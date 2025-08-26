# app/engine/signal_engine.py
from __future__ import annotations
# =============================================================================
# SIGNAL ENGINE FACADE
# -----------------------------------------------------------------------------
# - จุดศูนย์กลางรันเครื่องวิเคราะห์สัญญาณสำหรับ batch/cron หรือ webhook
# - ใช้ wave_service.analyze_wave เป็น core (สำหรับข้อความ/LINE)
# - มี process_ohlcv (compat สำหรับ unit tests เดิม: SMA/cooldown/TP-SL/alerts)
# =============================================================================

from typing import Dict, Optional, Any, List
import traceback
from types import SimpleNamespace

import pandas as pd
import numpy as np

from app.services.wave_service import analyze_wave, build_brief_message

__all__ = ["SignalEngine", "build_signal_payload", "build_line_text"]

# -----------------------------------------------------------------------------
# Core engine
# -----------------------------------------------------------------------------
class SignalEngine:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, *, xlsx_path: Optional[str] = None, **kwargs):
        base_cfg: Dict[str, Any] = {
            "min_candles": 30,
            "sma_fast": 10,
            "sma_slow": 30,
            "risk_pct": 0.01,
            "rr": 1.5,
            "cooldown_sec": 0,
            "move_alerts": [],
        }
        if cfg:
            base_cfg.update(cfg)
        if kwargs:
            base_cfg.update(kwargs)
        self.cfg: Dict[str, Any] = base_cfg
        self.xlsx_path = xlsx_path

        # state ต่อ symbol (สำหรับ compat engine)
        self._state: Dict[str, Dict[str, Any]] = {}
        # ให้เทสเข้าถึง/แก้ last_signal_ts และอ่าน last_alert_price ได้
        self._states: Dict[str, SimpleNamespace] = {}

    # --------- LINE / Wave facade ---------
    def analyze_symbol(
        self,
        symbol: str,
        tf: str = "1D",
        *,
        profile: Optional[str] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime_cfg = dict(self.cfg)
        if cfg:
            runtime_cfg.update(cfg)
        if profile:
            runtime_cfg["profile"] = profile

        try:
            payload = analyze_wave(symbol, tf=tf, xlsx_path=self.xlsx_path, cfg=runtime_cfg)
            text = build_brief_message(payload)
            return {
                "ok": True,
                "symbol": symbol,
                "tf": tf,
                "profile": runtime_cfg.get("profile", "baseline"),
                "text": text,
                "payload": payload,
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "symbol": symbol,
                "tf": tf,
                "profile": runtime_cfg.get("profile", "baseline"),
                "text": "",
                "payload": {},
                "error": f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}",
            }

    # --------- Helpers for compat engine ---------
    def _st(self, symbol: str) -> Dict[str, Any]:
        st = self._state.get(symbol)
        if st is None:
            st = {
                "pos": "NONE",        # NONE | LONG
                "entry": None,
                "tp": None,
                "sl": None,
                "move_anchor": None,
                "cooldown_until": None,  # pandas.Timestamp | None
            }
            self._state[symbol] = st
        return st

    @staticmethod
    def _sma(series: pd.Series, win: int) -> pd.Series:
        return series.rolling(win, min_periods=1).mean()

    @staticmethod
    def _last_ts(df: pd.DataFrame):
        ts = df.iloc[-1].get("timestamp")
        return pd.to_datetime(ts) if ts is not None else None

    def _ensure_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """สังเคราะห์คอลัมน์ที่จำเป็นจาก close หากขาด (สำหรับ unit tests)"""
        out = df.copy()
        if "close" not in out.columns:
            return out

        if "timestamp" not in out.columns:
            idx = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=len(out), freq="D")
            out["timestamp"] = idx

        if "open" not in out.columns:
            prev = out["close"].shift(1)
            out["open"] = prev.fillna(out["close"])

        if "high" not in out.columns:
            out["high"] = np.maximum(out["open"], out["close"])
        if "low" not in out.columns:
            out["low"] = np.minimum(out["open"], out["close"])

        return out

    def _pack(self, out: Dict[str, Any], *, pos_side: str, entry=None, tp=None, sl=None) -> Dict[str, Any]:
        """เติมคีย์มาตรฐานให้เทสอ่านได้เสมอ"""
        out["side"] = pos_side
        out["position"] = {
            "side": pos_side,
            "entry": entry,
            "tp": tp,
            "sl": sl,
        }
        return out

    # -----------------------------------------------------------------------------
    # Compat API สำหรับ unit tests เดิม
    # -----------------------------------------------------------------------------
    def process_ohlcv(self, symbol: str, df: pd.DataFrame, *, use_ai: bool = True) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "action": "HOLD",
            "pos": "NONE",
            "entry": None,
            "tp": None,
            "sl": None,
            "confidence": 50,
            "alerts": [],
            "reason": "",
            "analysis": {"pre_signal": {"confidence": 50}},
        }

        # (1) เช็กจำนวนแท่งก่อน
        min_candles = int(self.cfg.get("min_candles", 30))
        if len(df) < min_candles:
            out["reason"] = "insufficient_candles"
            return self._pack(out, pos_side="NONE")

        # (2) สังเคราะห์คอลัมน์ที่ขาด
        df = self._ensure_columns(df)
        required_cols = {"timestamp", "open", "high", "low", "close"}
        if not required_cols.issubset(df.columns):
            out["reason"] = "required columns missing"
            return self._pack(out, pos_side="NONE")

        # (3) เตรียมค่า
        st = self._st(symbol)
        ns = self._states.setdefault(symbol, SimpleNamespace(last_signal_ts=0, last_alert_price=None))

        ts_now = self._last_ts(df)
        close = float(df["close"].iloc[-1])
        open_ = float(df["open"].iloc[-1])

        sma_fast_n = int(self.cfg.get("sma_fast", 10))
        sma_slow_n = int(self.cfg.get("sma_slow", 30))
        sma_fast = float(self._sma(df["close"], sma_fast_n).iloc[-1])
        sma_slow = float(self._sma(df["close"], sma_slow_n).iloc[-1])

        is_green = close > open_
        cooldown_sec = int(self.cfg.get("cooldown_sec", 0))

        base_conf = 60 if use_ai else 55
        if sma_fast > sma_slow:
            base_conf += 5
        out["confidence"] = max(0, min(100, base_conf))
        out["analysis"]["pre_signal"]["confidence"] = out["confidence"]

        if ts_now is not None:
            try:
                ns.last_signal_ts = int(pd.Timestamp(ts_now).timestamp())
            except Exception:
                pass

        # (4) Cooldown
        if st.get("cooldown_until") is not None and ts_now is not None and ts_now < st["cooldown_until"]:
            out["reason"] = "cooldown"
            if st.get("pos") == "LONG":
                out.update({"pos": "LONG", "entry": st.get("entry"), "tp": st.get("tp"), "sl": st.get("sl")})
                return self._pack(out, pos_side="LONG", entry=st.get("entry"), tp=st.get("tp"), sl=st.get("sl"))
            return self._pack(out, pos_side="NONE")

        # (5) Position management
        pos = st.get("pos", "NONE")

        if pos == "LONG":
            entry = float(st["entry"])
            tp = float(st["tp"])
            sl = float(st["sl"])

            # TP
            if close >= tp:
                st.update({"pos": "NONE", "entry": None, "tp": None, "sl": None, "move_anchor": None})
                if cooldown_sec > 0 and ts_now is not None:
                    st["cooldown_until"] = ts_now + pd.Timedelta(seconds=cooldown_sec)
                out.update({"action": "CLOSE", "pos": "NONE", "entry": entry, "tp": tp, "sl": sl, "reason": "exit_tp"})
                return self._pack(out, pos_side="NONE")

            # SL
            if close <= sl:
                st.update({"pos": "NONE", "entry": None, "tp": None, "sl": None, "move_anchor": None})
                if cooldown_sec > 0 and ts_now is not None:
                    st["cooldown_until"] = ts_now + pd.Timedelta(seconds=cooldown_sec)
                out.update({"action": "CLOSE", "pos": "NONE", "entry": entry, "tp": tp, "sl": sl, "reason": "exit_sl"})
                return self._pack(out, pos_side="NONE")

            # ยังถืออยู่
            alerts = self._check_move_alerts(symbol, close)
            out["alerts"] = alerts
            out.update({"action": "HOLD", "pos": "LONG", "entry": entry, "tp": tp, "sl": sl, "reason": "in_position_no_flip"})
            return self._pack(out, pos_side="LONG", entry=entry, tp=tp, sl=sl)

        # Flat -> เปิด LONG เมื่อสัญญาณเข้า
        if sma_fast > sma_slow and is_green:
            entry = close
            risk_pct = float(self.cfg.get("risk_pct", 0.01))
            rr = float(self.cfg.get("rr", 1.5))
            risk_dist = entry * risk_pct
            sl = entry - risk_dist
            tp = entry + rr * risk_dist

            st.update({"pos": "LONG", "entry": float(entry), "tp": float(tp), "sl": float(sl), "move_anchor": float(entry)})
            # set last_alert_price เริ่มต้นเป็นราคาเข้า
            ns.last_alert_price = float(entry)

            out.update({"action": "OPEN", "pos": "LONG", "entry": entry, "tp": tp, "sl": sl, "reason": "sma_fast_gt_slow_and_green"})
            return self._pack(out, pos_side="LONG", entry=entry, tp=tp, sl=sl)

        out["reason"] = "no_condition_met"
        return self._pack(out, pos_side="NONE")

    # --------- Move alerts ---------
    def _check_move_alerts(self, symbol: str, last_price: float) -> List[str]:
        alerts_out: List[str] = []
        thresholds = list(self.cfg.get("move_alerts", []) or [])
        if not thresholds:
            return alerts_out

        st = self._st(symbol)
        ns = self._states.setdefault(symbol, SimpleNamespace(last_signal_ts=0, last_alert_price=None))
        anchor = st.get("move_anchor")

        # ตั้ง anchor / last_alert_price เริ่มต้น
        if anchor is None or (not isinstance(anchor, (int, float))):
            st["move_anchor"] = float(last_price)
            ns.last_alert_price = float(last_price)
            return alerts_out

        if anchor <= 0:
            st["move_anchor"] = float(last_price)
            ns.last_alert_price = float(last_price)
            return alerts_out

        chg = (last_price - anchor) / anchor
        for th in thresholds:
            try:
                thv = float(th)
            except Exception:
                continue
            if chg >= thv:
                alerts_out.append(f"MOVE_ALERT:+{int(thv*100)}% reached (from {anchor:,.2f} to {last_price:,.2f})")
                st["move_anchor"] = float(last_price)
                ns.last_alert_price = float(last_price)  # อัปเดตทุกครั้งที่ทริกเกอร์
        return alerts_out


# -----------------------------------------------------------------------------
# Convenience wrappers
# -----------------------------------------------------------------------------
def build_signal_payload(
    symbol: str,
    tf: str = "1D",
    *,
    profile: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    xlsx_path: Optional[str] = None,
) -> Dict[str, Any]:
    engine = SignalEngine(cfg=cfg, xlsx_path=xlsx_path)
    return engine.analyze_symbol(symbol, tf, profile=profile, cfg=cfg)

def build_line_text(
    symbol: str,
    tf: str = "1D",
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
