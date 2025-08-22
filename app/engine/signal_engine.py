# app/engine/signal_engine.py
from __future__ import annotations
# =============================================================================
# SIGNAL ENGINE FACADE
# -----------------------------------------------------------------------------
# - จุดศูนย์กลางรันเครื่องวิเคราะห์สัญญาณสำหรับงาน batch/cron หรือ webhook
# - ลำดับงาน: get_data → suggest_trade (profile-aware) → สร้าง payload/ข้อความ
# - รักษา backward compatibility กับโค้ดเดิม และรองรับ cfg ใน __init__
# =============================================================================

from typing import Dict, Optional, Any
import os
import traceback
import pandas as pd

from app.analysis.timeframes import get_data
from app.analysis.entry_exit import suggest_trade, format_trade_text
from app.analysis import indicators  # ใช้สร้างเหตุผล & % แนวโน้ม

__all__ = ["SignalEngine", "build_signal_payload", "build_line_text"]

# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v if v is not None and v != "" else default

DEFAULT_PROFILE = _env("STRATEGY_PROFILE", "baseline")  # fallback ถ้า caller ไม่ส่งมา

# ค่าตั้งต้นสำหรับเอนจิน (สามารถเติม/แก้ได้ตามต้องการ)
DEFAULT_CFG: Dict[str, Any] = {
    "min_candles": 30,
    "sma_fast": 10,
    "sma_slow": 30,
    "cooldown_sec": 0,
    "risk_pct": 0.01,
    "rr": 1.5,
    "move_alerts": [],
    # ช่องทางขยายในอนาคต...
}

# -----------------------------------------------------------------------------
# Helper: สร้างเหตุผลและ % แนวโน้ม
# -----------------------------------------------------------------------------
def _build_reasons_text(df: pd.DataFrame) -> str:
    rsi_val = indicators.rsi(df["close"], period=14).iloc[-1]
    ema20 = indicators.ema(df["close"], period=20).iloc[-1]
    ema50 = indicators.ema(df["close"], period=50).iloc[-1]
    macd_line, signal_line, hist = indicators.macd(df["close"])
    macd_val, signal_val, hist_val = macd_line.iloc[-1], signal_line.iloc[-1], hist.iloc[-1]

    reasons = []
    score_up, score_down = 0.0, 0.0

    # RSI
    if rsi_val < 45:
        reasons.append(f"RSI={rsi_val:.2f} → ใกล้ Oversold")
        score_up += 1
    elif rsi_val > 65:
        reasons.append(f"RSI={rsi_val:.2f} → ใกล้ Overbought")
        score_down += 1
    else:
        reasons.append(f"RSI={rsi_val:.2f} → Neutral")
        # ให้ bias ตาม EMA trend
        if ema20 > ema50:
            score_up += 0.5
        else:
            score_down += 0.5

    # EMA (น้ำหนักมากกว่า RSI)
    if ema20 > ema50:
        reasons.append("EMA20 > EMA50 → แนวโน้มขาขึ้นสั้น")
        score_up += 1.5
    else:
        reasons.append("EMA20 < EMA50 → แนวโน้มอ่อนตัว")
        score_down += 1.5

    # MACD
    if macd_val > signal_val:
        reasons.append("MACD > Signal → โมเมนตัมเริ่มบวก")
        score_up += 1
    else:
        reasons.append("MACD < Signal → โมเมนตัมลบ")
        score_down += 1

    # รวมคะแนน
    total = max(score_up + score_down, 1.0)
    up_pct = round(score_up / total * 100, 1)
    down_pct = round(score_down / total * 100, 1)

    reasons_text = "ℹ️ เหตุผลจากอินดิเคเตอร์\n- " + "\n- ".join(reasons)
    summary = f"\n\n📈 แนวโน้มโดยรวม:\n- ขาขึ้น: {up_pct}%\n- ขาลง: {down_pct}%"
    return reasons_text + summary

# -----------------------------------------------------------------------------
# Core engine
# -----------------------------------------------------------------------------
class SignalEngine:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, *, xlsx_path: Optional[str] = None, **kwargs):
        """
        รองรับทั้ง:
          - ส่ง dict ผ่าน cfg (รูปแบบที่ tests ใช้): SignalEngine(cfg={...})
          - ส่งคีย์เดี่ยว ๆ ผ่าน kwargs: SignalEngine(min_candles=50, sma_fast=10, ...)
        kwargs จะ override cfg; ทั้งหมดถูก merge เข้ากับ DEFAULT_CFG

        xlsx_path: override เส้นทางไฟล์ historical.xlsx ได้ถ้าต้องการ
        """
        base = dict(DEFAULT_CFG)
        if cfg:
            base.update(cfg)
        if kwargs:
            base.update(kwargs)

        self.cfg: Dict[str, Any] = base
        self.xlsx_path = xlsx_path

        # map เป็นแอตทริบิวต์เพื่อความสะดวก / compat
        for k, v in base.items():
            setattr(self, k, v)

        # state เริ่มต้น (หากโค้ดส่วนอื่นต้องการ)
        self._last_open_ts = getattr(self, "_last_open_ts", None)
        self._position = getattr(self, "_position", None)

    def analyze_symbol(
        self,
        symbol: str,
        tf: str,
        *,
        profile: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        วิเคราะห์สัญญาณหนึ่งชุดและคืน payload พร้อมข้อความสำหรับส่ง LINE
        """
        # merge cfg ที่ส่งมาระดับเมธอดกับ cfg ของเอนจิน
        runtime_cfg = dict(self.cfg)
        if cfg:
            runtime_cfg.update(cfg)

        use_profile = (profile or runtime_cfg.get("profile") or DEFAULT_PROFILE) or "baseline"

        try:
            # 1) Load OHLCV
            df = get_data(symbol, tf, xlsx_path=self.xlsx_path)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {
                    "ok": False,
                    "symbol": symbol,
                    "tf": tf,
                    "profile": use_profile,
                    "text": "",
                    "trade": {},
                    "error": "No data loaded for symbol/timeframe.",
                }

            # 2) Build trade suggestion
            trade = suggest_trade(
                df,
                symbol=symbol,
                tf=tf,
                cfg={**runtime_cfg, "profile": use_profile},
            )

            # 3) Compose short text (ของเดิม)
            base_text = format_trade_text(trade)
            base_text = base_text.replace("ℹ️ เหตุผล:", "").strip()

            # 4) Append เหตุผล + % ขึ้นลง
            reasons_text = _build_reasons_text(df)
            text = f"{base_text}\n\n{reasons_text}"

            return {
                "ok": True,
                "symbol": symbol,
                "tf": tf,
                "profile": use_profile,
                "text": text,
                "trade": trade,
                "error": None,
            }

        except Exception as e:
            return {
                "ok": False,
                "symbol": symbol,
                "tf": tf,
                "profile": use_profile,
                "text": "",
                "trade": {},
                "error": f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}",
            }

# -----------------------------------------------------------------------------
# Convenience wrappers (backward-compatible)
# -----------------------------------------------------------------------------
def build_signal_payload(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> Dict[str, Any]:
    engine = SignalEngine(cfg=cfg, xlsx_path=xlsx_path)
    return engine.analyze_symbol(symbol, tf, profile=profile, cfg=cfg)

def build_line_text(
    symbol: str,
    tf: str,
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> str:
    payload = build_signal_payload(symbol, tf, profile=profile, cfg=cfg, xlsx_path=xlsx_path)
    if payload.get("ok"):
        return payload.get("text", "")
    err = payload.get("error") or "unknown error"
    return f"❗️Signal error: {err}"
