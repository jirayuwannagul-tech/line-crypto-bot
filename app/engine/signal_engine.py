# app/engine/signal_engine.py
from __future__ import annotations
# =============================================================================
# SIGNAL ENGINE FACADE
# -----------------------------------------------------------------------------
# - จุดศูนย์กลางรันเครื่องวิเคราะห์สัญญาณสำหรับงาน batch/cron หรือ webhook
# - ลำดับงาน: get_data → suggest_trade (profile-aware) → สร้าง payload/ข้อความ
# - รักษา backward compatibility กับโค้ดเดิม และรองรับ cfg ใน __init__
# =============================================================================

from typing import Dict, Optional, Any, List
import os
import time
import traceback
from types import SimpleNamespace
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

# ค่าตั้งต้นสำหรับเอนจิน
DEFAULT_CFG: Dict[str, Any] = {
    "min_candles": 30,
    "sma_fast": 10,
    "sma_slow": 30,
    "cooldown_sec": 0,
    "risk_pct": 0.01,   # 1% stop
    "rr": 1.5,          # take-profit = risk_pct * rr
    "move_alerts": [],  # เช่น [0.01, 0.02]
}

# -----------------------------------------------------------------------------
# Helper: สร้างเหตุผลและ % แนวโน้ม (ใช้กับ build_line_text/analyze_symbol)
# -----------------------------------------------------------------------------
def _build_reasons_text(df: pd.DataFrame) -> str:
    rsi_val = indicators.rsi(df["close"], period=14).iloc[-1]
    ema20 = indicators.ema(df["close"], period=20).iloc[-1]
    ema50 = indicators.ema(df["close"], period=50).iloc[-1]
    macd_line, signal_line, hist = indicators.macd(df["close"])
    macd_val, signal_val, hist_val = macd_line.iloc[-1], signal_line.iloc[-1], hist.iloc[-1]

    reasons: List[str] = []
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
        if ema20 > ema50:
            score_up += 0.5
        else:
            score_down += 0.5

    # EMA (ให้น้ำหนักมากกว่า RSI)
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

        # สถานะต่อสัญลักษณ์
        # _pos: {symbol: {side, entry, tp, sl, anchor}}
        self._pos: Dict[str, Dict[str, Any]] = {}
        # _states: {symbol: SimpleNamespace(last_signal_ts=float, last_alert_price=float)}
        self._states: Dict[str, SimpleNamespace] = {}

    def _ensure_state(self, symbol: str) -> SimpleNamespace:
        st = self._states.get(symbol)
        if st is None:
            st = SimpleNamespace(last_signal_ts=0.0, last_alert_price=None)
            self._states[symbol] = st
        return st

    def _position_dict(self, pos: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not pos:
            return {"side": "NONE"}
        return {
            "side": pos.get("side", "NONE"),
            "entry": pos.get("entry"),
            "tp": pos.get("tp"),
            "sl": pos.get("sl"),
            "anchor": pos.get("anchor"),
        }

    # ===== method ที่เทสเรียกใช้ =====
    def process_ohlcv(self, symbol: str, df: pd.DataFrame, *, use_ai: bool = False) -> Dict[str, Any]:
        """
        ประมวลผลสัญญาณจาก DataFrame ที่ caller เตรียมให้
        Expected df columns: ['open','high','low','close']
        Behavior ให้ตรงกับ tests:
          - น้อยกว่า min_candles → HOLD (reason=insufficient_candles)
          - ไม่มีสถานะ และ SMA_fast > SMA_slow และแท่งล่าสุดเขียว และไม่ติด cooldown → OPEN LONG
          - มีสถานะ LONG:
              - CLOSE เมื่อแตะ TP/SL (ไม่ flip)
              - ไม่ถึง TP/SL → HOLD (reason=in_position_no_flip)
          - รองรับ move_alerts: ยิง alerts และอัปเดต anchor
          - คืน analysis.pre_signal.confidence เสมอ
          - คืน position เสมอ (ถ้าไม่มี → side=NONE)
          - บน OPEN ต้องมีคีย์ระดับบน: tp, sl
          - มี _states[symbol].last_alert_price และอัปเดตเมื่อเปิด/เกิด move alert
        """
        # analysis.pre_signal.confidence
        if len(df) > 0:
            close = df["close"].iloc[-1]
            open_ = df["open"].iloc[-1]
        else:
            close = open_ = None

        conf = 0.5
        if len(df) >= max(int(self.cfg["sma_fast"]), int(self.cfg["sma_slow"])):
            fast_n = int(self.cfg["sma_fast"])
            slow_n = int(self.cfg["sma_slow"])
            sma_fast = df["close"].rolling(window=fast_n).mean().iloc[-1]
            sma_slow = df["close"].rolling(window=slow_n).mean().iloc[-1]
            if sma_fast > sma_slow:
                conf += 0.2
        if close is not None and open_ is not None and close > open_:
            conf += 0.2
        if use_ai:
            conf += 0.1
        conf = max(0.0, min(1.0, conf))

        pos = self._pos.get(symbol)
        out: Dict[str, Any] = {
            "symbol": symbol,
            "action": "HOLD",
            "reason": None,
            "side": None,
            "analysis": {"pre_signal": {"confidence": conf}},
            "alerts": [],
            "position": self._position_dict(pos),
        }

        # 0) ตรวจจำนวนแท่งข้อมูล
        if len(df) < int(self.cfg["min_candles"]):
            out["reason"] = "insufficient_candles"
            return out

        # 1) SMA และเขียว/แดงของแท่งล่าสุด
        fast_n = int(self.cfg["sma_fast"])
        slow_n = int(self.cfg["sma_slow"])
        sma_fast = df["close"].rolling(window=fast_n).mean().iloc[-1]
        sma_slow = df["close"].rolling(window=slow_n).mean().iloc[-1]

        st = self._ensure_state(symbol)

        # 2) ถ้ามีสถานะ LONG อยู่แล้ว → ตรวจ TP/SL และ move_alerts
        if pos and pos.get("side") == "LONG":
            entry = float(pos["entry"])
            tp = float(pos["tp"])
            sl = float(pos["sl"])
            anchor = float(pos.get("anchor", entry))
            cur = float(df["close"].iloc[-1])

            # move alerts
            alerts: List[str] = []
            for th in sorted(self.cfg.get("move_alerts", [])):
                if th and th > 0 and cur >= anchor * (1 + th):
                    alerts.append(f"up_{round(th * 100, 1)}%")
                    anchor = anchor * (1 + th)
            if alerts:
                out["alerts"] = alerts
                pos["anchor"] = anchor
                st.last_alert_price = anchor  # อัปเดต state
                out["position"] = self._position_dict(pos)

            # TP / SL
            if cur >= tp:
                pnl = (cur - entry) / entry
                closed_pos = self._position_dict(pos)
                self._pos.pop(symbol, None)
                out.update({
                    "action": "CLOSE",
                    "side": "LONG",
                    "reason": "take_profit",
                    "pnl": pnl,
                    "position": closed_pos,
                })
                return out
            if cur <= sl:
                pnl = (cur - entry) / entry
                closed_pos = self._position_dict(pos)
                self._pos.pop(symbol, None)
                out.update({
                    "action": "CLOSE",
                    "side": "LONG",
                    "reason": "stop_loss",
                    "pnl": pnl,
                    "position": closed_pos,
                })
                return out

            # ไม่ถึง TP/SL → HOLD ไม่ flip
            out.update({
                "action": "HOLD",
                "side": "LONG",
                "reason": "in_position_no_flip",
                "position": self._position_dict(pos),
            })
            return out

        # 3) ยังไม่มีสถานะ → พิจารณาเปิด LONG (เช็ก cooldown ก่อน)
        now = time.time()
        cooldown = float(self.cfg.get("cooldown_sec", 0) or 0)
        if cooldown > 0 and (now - (st.last_signal_ts or 0)) < cooldown:
            out.update({"reason": "cooldown"})
            return out

        # เงื่อนไขเปิด: fast > slow และแท่งล่าสุดเขียว
        cur_close = float(df["close"].iloc[-1])
        cur_open = float(df["open"].iloc[-1])
        if sma_fast > sma_slow and cur_close > cur_open:
            entry = cur_close
            risk_pct = float(self.cfg["risk_pct"])
            rr = float(self.cfg["rr"])
            sl = entry * (1.0 - risk_pct)
            tp = entry * (1.0 + risk_pct * rr)
            new_pos = {
                "side": "LONG",
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "anchor": entry,
            }
            self._pos[symbol] = new_pos
            st.last_signal_ts = now
            st.last_alert_price = entry  # ตั้ง anchor เริ่มต้นสำหรับ state

            out.update({
                "action": "OPEN",
                "side": "LONG",
                "reason": "new_long",
                "position": self._position_dict(new_pos),
                # >>> คีย์ระดับบนที่เทสต้องการ
                "tp": tp,
                "sl": sl,
            })
            return out

        # ไม่เข้าเงื่อนไขเปิด
        out.update({"reason": "no_setup"})
        return out

    # ===== วิเคราะห์ด้วย data loader ภายใน และ compose ข้อความสำหรับ LINE =====
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
