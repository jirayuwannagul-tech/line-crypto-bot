# app/engine/signal_engine.py
# =============================================================================
# Signal Engine (Mock Logic) — with Pylance‑friendly type hints
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal, List

# ---- ใช้ DataFrame เป็นชนิดกลางสำหรับ type hints (fallback ได้) -------------
try:
    import pandas as pd  # runtime ใช้งานจริง
    from pandas import DataFrame  # สำหรับ type hints
except Exception:  # pragma: no cover
    pd = None  # type: ignore

    class DataFrame:  # type: ignore
        """Placeholder for typing when pandas is unavailable."""
        pass

Side = Literal["NONE", "LONG", "SHORT"]

DEFAULT_CFG: Dict[str, Any] = {
    "min_candles": 30,
    "sma_fast": 10,
    "sma_slow": 30,
    "risk_pct": 0.01,
    "rr": 1.5,
    "cooldown_sec": 30,
    "move_alerts": [0.01, 0.02],
}

@dataclass
class Position:
    side: Side = "NONE"
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    opened_ts: Optional[float] = None

@dataclass
class SymbolState:
    last_signal_ts: float = 0.0
    position: Position = field(default_factory=Position)
    last_alert_price: Optional[float] = None

class SignalEngine:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, use_ai: bool = False) -> None:
        self.cfg: Dict[str, Any] = {**DEFAULT_CFG, **(cfg or {})}
        self._states: Dict[str, SymbolState] = {}
        self._use_ai: bool = bool(use_ai)

    def set_ai(self, enabled: bool) -> None:
        self._use_ai = bool(enabled)

    def reset_symbol(self, symbol: str) -> None:
        self._states.pop(symbol, None)

    def process_ohlcv(self, symbol: str, df: DataFrame, use_ai: Optional[bool] = None) -> Dict[str, Any]:
        st = self._states.setdefault(symbol, SymbolState())
        now = time.time()

        if pd is None or df is None:
            return self._pack(st, action="HOLD", side=st.position.side, price=None,
                              reason="pandas_unavailable_or_df_missing", analysis={})

        needed = {"open", "high", "low", "close"}
        if not needed.issubset(getattr(df, "columns", [])):
            return self._pack(st, action="HOLD", side=st.position.side, price=None,
                              reason="invalid_df_columns", analysis={"columns": list(getattr(df, "columns", []))})

        if len(df) < int(self.cfg["min_candles"]):
            return self._pack(st, action="HOLD", side=st.position.side, price=None,
                              reason="insufficient_candles", analysis={"rows": int(len(df))})

        last_price = float(df["close"].iloc[-1])

        ind_result: Dict[str, Any] = self._analyze_with_indicators(df)

        use_ai_flag: bool = self._use_ai if use_ai is None else bool(use_ai)
        ai_result: Dict[str, Any] = self._analyze_with_ai(ind_result) if use_ai_flag else {}

        pre: Dict[str, Any] = self._combine_pre_signal(ind_result, ai_result, use_ai_flag)

        if st.position.side != "NONE" and st.position.entry is not None:
            hit, which = self._check_tp_sl(st.position, last_price)
            if hit:
                prev_side = st.position.side
                self._close_position(st)
                return self._pack(st, action="CLOSE", side=prev_side, price=last_price,
                                  reason=f"exit_{which}", analysis={"pre_signal": pre, "ai_used": use_ai_flag})

            alerts: List[str] = self._check_move_alerts(st, last_price)
            if alerts:
                return self._pack(st, action="ALERT", side=st.position.side, price=last_price,
                                  reason="; ".join(alerts), analysis={"pre_signal": pre, "ai_used": use_ai_flag})

            return self._pack(st, action="HOLD", side=st.position.side, price=last_price,
                              reason="in_position_no_flip", analysis={"pre_signal": pre, "ai_used": use_ai_flag})

        if now - st.last_signal_ts < float(self.cfg["cooldown_sec"]):
            return self._pack(st, action="HOLD", side="NONE", price=last_price,
                              reason="cooldown", analysis={"pre_signal": pre, "ai_used": use_ai_flag})

        if pre.get("bias") == "long":
            self._open_position(st, side="LONG", entry=last_price)
            st.last_signal_ts = now
            return self._pack(st, action="OPEN", side="LONG", price=last_price,
                              reason="pre_signal_long", analysis={"pre_signal": pre, "ai_used": use_ai_flag})

        if pre.get("bias") == "short":
            self._open_position(st, side="SHORT", entry=last_price)
            st.last_signal_ts = now
            return self._pack(st, action="OPEN", side="SHORT", price=last_price,
                              reason="pre_signal_short", analysis={"pre_signal": pre, "ai_used": use_ai_flag})

        return self._pack(st, action="HOLD", side="NONE", price=last_price,
                          reason="pre_signal_neutral", analysis={"pre_signal": pre, "ai_used": use_ai_flag})

    # ---- Analysis (mock) ----------------------------------------------------

    def _analyze_with_indicators(self, df: DataFrame) -> Dict[str, Any]:
        close = df["close"]
        open_ = df["open"]

        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_close
        last_open = float(open_.iloc[-1])

        sma_fast = float(close.rolling(int(self.cfg["sma_fast"])).mean().iloc[-1])
        sma_slow = float(close.rolling(int(self.cfg["sma_slow"])).mean().iloc[-1])

        bias = "neutral"
        if sma_fast > sma_slow and last_close >= last_open:
            bias = "long"
        elif sma_fast < sma_slow and last_close <= last_open:
            bias = "short"

        confidence = 0.6 if bias != "neutral" else 0.5

        return {
            "last_close": last_close,
            "prev_close": prev_close,
            "last_open": last_open,
            "sma_fast": sma_fast,
            "sma_slow": sma_slow,
            "bias": bias,
            "confidence": confidence,
            "notes": "mock_indicators",
        }

    def _analyze_with_ai(self, indicator_result: Dict[str, Any]) -> Dict[str, Any]:
        base_bias = indicator_result.get("bias", "neutral")
        base_conf = float(indicator_result.get("confidence", 0.5))
        ai_conf_boost = 0.1 if base_bias != "neutral" else 0.0
        return {
            "ai_bias_hint": base_bias,
            "ai_confidence": min(1.0, base_conf + ai_conf_boost),
            "ai_notes": "mock_ai_inference",
        }

    def _combine_pre_signal(self, ind_res: Dict[str, Any], ai_res: Dict[str, Any], ai_used: bool) -> Dict[str, Any]:
        bias = ind_res.get("bias", "neutral")
        conf = float(ind_res.get("confidence", 0.5))
        if ai_used and ai_res:
            conf = float(ai_res.get("ai_confidence", conf))
        return {
            "bias": bias,
            "confidence": conf,
            "sources": {"indicators": ind_res, "ai": ai_res if ai_used else None},
            "strategy_id": "mock_momentum_breakout",
        }

    # ---- Position & Risk helpers -------------------------------------------

    def _open_position(self, st: SymbolState, side: Side, entry: float) -> None:
        risk_d = float(self.cfg["risk_pct"]) * entry
        rr = float(self.cfg["rr"])
        if side == "LONG":
            sl = max(0.0, entry - risk_d)
            tp = entry + rr * risk_d
        elif side == "SHORT":
            sl = entry + risk_d
            tp = max(0.0, entry - rr * risk_d)
        else:
            sl = None
            tp = None
        st.position = Position(side=side, entry=entry, sl=sl, tp=tp, opened_ts=time.time())
        st.last_alert_price = entry

    def _close_position(self, st: SymbolState) -> None:
        st.position = Position()
        st.last_alert_price = None

    def _check_tp_sl(self, pos: Position, price: float) -> tuple[bool, str]:
        if pos.side == "LONG":
            if pos.tp is not None and price >= pos.tp:
                return True, "tp"
            if pos.sl is not None and price <= pos.sl:
                return True, "sl"
        elif pos.side == "SHORT":
            if pos.tp is not None and price <= pos.tp:
                return True, "tp"
            if pos.sl is not None and price >= pos.sl:
                return True, "sl"
        return False, ""

    def _check_move_alerts(self, st: SymbolState, price: float) -> List[str]:
        if st.last_alert_price is None or st.last_alert_price <= 0:
            return []
        base = st.last_alert_price
        pct = (price - base) / base
        alerts: List[str] = []
        for th_raw in self.cfg.get("move_alerts", []):
            th = float(th_raw)
            if pct >= th:
                alerts.append(f"moved +{int(th*100)}%")
            elif pct <= -th:
                alerts.append(f"moved -{int(th*100)}%")
        if alerts:
            st.last_alert_price = price
        return alerts

    def _pack(
        self,
        st: SymbolState,
        action: Literal["OPEN", "HOLD", "CLOSE", "ALERT"],
        side: Side,
        price: Optional[float],
        reason: str,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        pos = st.position
        return {
            "action": action,
            "side": side,
            "price": price,
            "sl": pos.sl,
            "tp": pos.tp,
            "reason": reason,
            "analysis": analysis,
            "position": {
                "side": pos.side,
                "entry": pos.entry,
                "sl": pos.sl,
                "tp": pos.tp,
                "opened_ts": pos.opened_ts,
            },
        }
