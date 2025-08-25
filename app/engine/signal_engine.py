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
from datetime import timedelta
import math

import pandas as pd

from app.services.wave_service import analyze_wave, build_brief_message

__all__ = ["SignalEngine", "build_signal_payload", "build_line_text"]

# -----------------------------------------------------------------------------
# Core engine
# -----------------------------------------------------------------------------
class SignalEngine:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, *, xlsx_path: Optional[str] = None, **kwargs):
        # config สำหรับ LINE/wave + สำหรับ process_ohlcv (compat tests)
        base_cfg: Dict[str, Any] = {
            # --- สำหรับ process_ohlcv ---
            "min_candles": 30,
            "sma_fast": 10,
            "sma_slow": 30,
            "risk_pct": 0.01,      # 1% ของราคาเป็นความเสี่ยง (ใช้คำนวณ SL/TP)
            "rr": 1.5,             # reward : risk
            "cooldown_sec": 0,     # ไม่คูลดาวน์โดยค่าเริ่มต้น
            "move_alerts": [],     # เช่น [0.01] = +1% จาก anchor จะยิง alert
        }
        if cfg:
            base_cfg.update(cfg)
        if kwargs:
            base_cfg.update(kwargs)
        self.cfg: Dict[str, Any] = base_cfg
        self.xlsx_path = xlsx_path

        # state ต่อ symbol (ใช้โดย process_ohlcv)
        self._state: Dict[str, Dict[str, Any]] = {}

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
                "move_anchor": None,  # ราคาอ้างอิงไว้เช็ก move alerts
                "cooldown_until": None,  # pandas.Timestamp หรือ None
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

    # -----------------------------------------------------------------------------
    # Compat API สำหรับ unit tests เดิม
    # -----------------------------------------------------------------------------
    def process_ohlcv(self, symbol: str, df: pd.DataFrame, *, use_ai: bool = True) -> Dict[str, Any]:
        """
        Logic แบบบางเบา (SMA-based) เพื่อให้ unit tests เดิมผ่าน:
        - ถ้าข้อมูลน้อยกว่า min_candles -> HOLD
        - หากไม่มีสถานะ: เปิด LONG เมื่อ SMA(fast) > SMA(slow) และแท่งล่าสุดเขียว
        - หากมีสถานะ LONG: ปิดเมื่อถึง TP หรือ SL
        - เคารพ cooldown_sec หลังปิดสถานะ
        - ส่ง move alerts เมื่อราคาขยับจาก anchor ตาม thresholds
        - use_ai=True จะเพิ่ม confidence เล็กน้อย (ไม่ใช่เงื่อนไขบังคับ)
        """
        out: Dict[str, Any] = {
            "action": "HOLD",
            "pos": "NONE",
            "entry": None,
            "tp": None,
            "sl": None,
            "confidence": 50,
            "alerts": [],   # รายการข้อความ/อ็อบเจ็กต์แจ้งเตือน
            "reason": "",
        }

        # ป้องกันคอลัมน์ไม่ครบ
        required_cols = {"timestamp", "open", "high", "low", "close"}
        if not required_cols.issubset(df.columns):
            out["reason"] = "required columns missing"
            return out

        # min candles
        min_candles = int(self.cfg.get("min_candles", 30))
        if len(df) < min_candles:
            out["reason"] = "insufficient candles"
            return out

        # เตรียมค่า
        st = self._st(symbol)
        ts_now = self._last_ts(df)
        close = float(df["close"].iloc[-1])
        open_ = float(df["open"].iloc[-1])

        sma_fast_n = int(self.cfg.get("sma_fast", 10))
        sma_slow_n = int(self.cfg.get("sma_slow", 30))
        sma_fast = self._sma(df["close"], sma_fast_n).iloc[-1]
        sma_slow = self._sma(df["close"], sma_slow_n).iloc[-1]

        is_green = close > open_
        cooldown_sec = int(self.cfg.get("cooldown_sec", 0))

        # confidence (ไม่ใช่ gating)
        base_conf = 60 if use_ai else 55
        # เพิ่ม/ลดนิดหน่อยตามแนวโน้ม SMA
        if sma_fast > sma_slow:
            base_conf += 5
        out["confidence"] = max(0, min(100, base_conf))

        # ตรวจ cooldown
        if st.get("cooldown_until") is not None and ts_now is not None:
            if ts_now < st["cooldown_until"]:
                # อยู่ในช่วง cooldown -> ห้ามเปิดใหม่
                pass
            else:
                st["cooldown_until"] = None

        # ============ Position management ============
        pos = st.get("pos", "NONE")

        # ---- If in position (LONG) -> manage exits ----
        if pos == "LONG":
            entry = float(st["entry"])
            tp = float(st["tp"])
            sl = float(st["sl"])

            # ปิดที่ TP
            if close >= tp:
                st["pos"] = "NONE"
                st["entry"] = None
                st["tp"] = None
                st["sl"] = None
                if cooldown_sec > 0 and ts_now is not None:
                    st["cooldown_until"] = ts_now + pd.Timedelta(seconds=cooldown_sec)
                out.update({"action": "CLOSE", "pos": "NONE", "entry": entry, "tp": tp, "sl": sl, "reason": "tp hit"})
                # reset move anchor เมื่อปิด
                st["move_anchor"] = None
                return out

            # ปิดที่ SL
            if close <= sl:
                st["pos"] = "NONE"
                st["entry"] = None
                st["tp"] = None
                st["sl"] = None
                if cooldown_sec > 0 and ts_now is not None:
                    st["cooldown_until"] = ts_now + pd.Timedelta(seconds=cooldown_sec)
                out.update({"action": "CLOSE", "pos": "NONE", "entry": entry, "tp": tp, "sl": sl, "reason": "sl hit"})
                st["move_anchor"] = None
                return out

            # ยังถืออยู่ -> ตรวจ move alerts
            alerts = self._check_move_alerts(symbol, close)
            out["alerts"] = alerts
            out.update({"action": "HOLD", "pos": "LONG", "entry": entry, "tp": tp, "sl": sl})
            return out

        # ---- If flat (NONE) -> consider opens ----
        # ห้ามเปิดถ้าอยู่ใน cooldown
        if st.get("cooldown_until") is not None and ts_now is not None:
            if ts_now < st["cooldown_until"]:
                out["reason"] = "in cooldown"
                return out
            else:
                st["cooldown_until"] = None

        # เงื่อนไขเปิด LONG: SMA fast > slow และแท่งเขียว
        if sma_fast > sma_slow and is_green:
            entry = close
            risk_pct = float(self.cfg.get("risk_pct", 0.01))
            rr = float(self.cfg.get("rr", 1.5))
            # ระยะเสี่ยง = entry * risk_pct
            risk_dist = entry * risk_pct
            sl = entry - risk_dist
            tp = entry + rr * risk_dist

            st["pos"] = "LONG"
            st["entry"] = float(entry)
            st["tp"] = float(tp)
            st["sl"] = float(sl)
            st["move_anchor"] = float(entry)  # เริ่มจับการขยับจากราคาเข้า

            out.update({"action": "OPEN_LONG", "pos": "LONG", "entry": entry, "tp": tp, "sl": sl, "reason": "sma_fast>slow & green"})
            return out

        # ไม่เข้าเงื่อนไข -> HOLD
        out["reason"] = "no condition met"
        return out

    # --------- Move alerts ---------
    def _check_move_alerts(self, symbol: str, last_price: float) -> List[str]:
        """
        ตรวจการขยับจาก anchor ตาม thresholds (เช่น [0.01] = +1%)
        เมื่อทริกเกอร์แล้ว จะเลื่อน anchor ไปเป็นราคาปัจจุบัน
        """
        alerts_out: List[str] = []
        thresholds = list(self.cfg.get("move_alerts", []) or [])
        if not thresholds:
            return alerts_out

        st = self._st(symbol)
        anchor = st.get("move_anchor")
        if anchor is None or (not isinstance(anchor, (int, float))):
            st["move_anchor"] = float(last_price)
            return alerts_out

        # คำนวณการเปลี่ยนแปลงสัมพัทธ์
        if anchor <= 0:
            st["move_anchor"] = float(last_price)
            return alerts_out

        chg = (last_price - anchor) / anchor
        for th in thresholds:
            try:
                thv = float(th)
            except Exception:
                continue
            if chg >= thv:
                alerts_out.append(f"MOVE_ALERT:+{int(thv*100)}% reached (from {anchor:,.2f} to {last_price:,.2f})")
                # อัปเดต anchor เพื่อรอรอบถัดไป
                st["move_anchor"] = float(last_price)
                # หมายเหตุ: ไม่ break เพื่อรองรับหลาย threshold ที่ต่ำกว่า
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
