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

DEFAULT_PROFILE = _env("STRATEGY_PROFILE", "baseline")

DEFAULT_CFG: Dict[str, Any] = {
    "min_candles": 30,
    "sma_fast": 10,
    "sma_slow": 30,
    "cooldown_sec": 0,
    "risk_pct": 0.01,
    "rr": 1.5,
    "move_alerts": [],
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

    reasons: List[str] = []
    score_up, score_down = 0.0, 0.0

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

    if ema20 > ema50:
        reasons.append("EMA20 > EMA50 → แนวโน้มขาขึ้นสั้น")
        score_up += 1.5
    else:
        reasons.append("EMA20 < EMA50 → แนวโน้มอ่อนตัว")
        score_down += 1.5

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
        base = dict(DEFAULT_CFG)
        if cfg:
            base.update(cfg)
        if kwargs:
            base.update(kwargs)

        self.cfg: Dict[str, Any] = base
        self.xlsx_path = xlsx_path

        for k, v in base.items():
            setattr(self, k, v)

        self._pos: Dict[str, Dict[str, Any]] = {}
        # _states: {symbol: SimpleNamespace(last_signal_ts=float, last_alert_price=float|None)}
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

    def process_ohlcv(self, symbol: str, df: pd.DataFrame, *, use_ai: bool = False) -> Dict[str, Any]:
        # --- analysis.pre_signal.confidence ---
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

        # --- checks ---
        if len(df) < int(self.cfg["min_candles"]):
            out["reason"] = "insufficient_candles"
            return out

        fast_n = int(self.cfg["sma_fast"])
        slow_n = int(self.cfg["sma_slow"])
        sma_fast = df["close"].rolling(window=fast_n).mean().iloc[-1]
        sma_slow = df["close"].rolling(window=slow_n).mean().iloc[-1]

        st = self._ensure_state(symbol)

        # --- if in position: manage & exit ---
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
                st.last_alert_price = anchor
                out["position"] = self._position_dict(pos)

            # exits
            if cur >= tp:
                pnl = (cur - entry) / entry
                self._pos.pop(symbol, None)
                out.update({
                    "action": "CLOSE",
                    "side": "LONG",
                    "reason": "exit_tp",
                    "pnl": pnl,
                    "position": {"side": "NONE"},  # ✅ หลังปิดต้อง NONE
                })
                return out
            if cur <= sl:
                pnl = (cur - entry) / entry
                self._pos.pop(symbol, None)
                out.update({
                    "action": "CLOSE",
                    "side": "LONG",
                    "reason": "exit_sl",
                    "pnl": pnl,
                    "position": {"side": "NONE"},  # ✅ หลังปิดต้อง NONE
                })
                return out

            out.update({
                "action": "HOLD",
                "side": "LONG",
                "reason": "in_position_no_flip",
                "position": self._position_dict(pos),
            })
            return out

        # --- consider open ---
        now = time.time()
        cooldown = float(self.cfg.get("cooldown_sec", 0) or 0)
        if cooldown > 0 and (now - (st.last_signal_ts or 0)) < cooldown:
            out.update({"reason": "cooldown"})
            return out

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
            st.last_alert_price = entry

            out.update({
                "action": "OPEN",
                "side": "LONG",
                "reason": "new_long",
                "position": self._position_dict(new_pos),
                "tp": tp,  # คีย์ระดับบนที่เทสต้องการ
                "sl": sl,
            })
            return out

        out.update({"reason": "no_setup"})
        return out

    # ===== สำหรับใช้งานกับ data loader ภายใน และ compose ข้อความ LINE =====
    def analyze_symbol(
        self,
        symbol: str,
        tf: str,
        *,
        profile: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime_cfg = dict(self.cfg)
        if cfg:
            runtime_cfg.update(cfg)

        use_profile = (profile or runtime_cfg.get("profile") or DEFAULT_PROFILE) or "baseline"

        try:
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

            trade = suggest_trade(
                df,
                symbol=symbol,
                tf=tf,
                cfg={**runtime_cfg, "profile": use_profile},
            )

            base_text = format_trade_text(trade).replace("ℹ️ เหตุผล:", "").strip()
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
# Convenience wrappers
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
