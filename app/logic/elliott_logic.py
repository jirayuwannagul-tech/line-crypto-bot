# app/logic/elliott_logic.py
# ============================================================
# Logic layer: wrap classify_elliott() ให้คืน "kind" ที่คงเส้นคงวา
# โดยอาศัย context (EMA slope, ATR, swing fail ฯลฯ)
# ไม่แก้ของเดิม — เพิ่มฟังก์ชันใหม่อย่างเดียว
# ============================================================

from __future__ import annotations
import math
import pandas as pd

# สมมติว่าไฟล์นี้เดิมมีฟังก์ชัน classify_elliott(df) อยู่แล้ว
# from .somewhere import classify_elliott  # <- ถ้าของเดิม import แบบนี้
# ในโปรเจกต์คุณไฟล์นี้น่าจะมี classify_elliott อยู่แล้วตามที่ test script ใช้

# -------------------- Helpers (ใหม่) --------------------
def _ema(series: pd.Series, span=20) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def enrich_context(df_ctx: pd.DataFrame, det: dict) -> dict:
    """
    เติมข้อมูล context ลง det['current']:
    - ema20_slope  : ค่าชัน EMA20 (อัตราส่วน)
    - atr_pct      : ATR เทียบกับ close
    - recent_direction: ทิศทาง 5 แท่งล่าสุด (up/down/side)
    - swing_fail   : สัญญาณยอดอ่อนแรง (อยู่ใต้ EMA20 และทำ Lower High)
    """
    if not isinstance(det, dict):
        return det
    cur = det.get("current", {}) or {}

    if df_ctx is None or len(df_ctx) < 25:
        det["current"] = cur
        return det

    df = df_ctx.sort_values("date").tail(120).reset_index(drop=True)
    close = df["close"]
    high, low = df["high"], df["low"]

    ema20 = _ema(close, span=20)
    base = ema20.iloc[-5] if len(ema20) >= 6 else ema20.iloc[0]
    ema20_slope = float((ema20.iloc[-1] - base) / (base if base != 0 else 1e-9))

    atr14 = _atr(df, 14)
    atr_pct = float(atr14.iloc[-1] / (close.iloc[-1] if close.iloc[-1] != 0 else 1e-9))

    recent_direction = "side"
    if len(close) >= 6:
        if close.iloc[-1] > close.iloc[-5] * 1.002:
            recent_direction = "up"
        elif close.iloc[-1] < close.iloc[-5] * 0.998:
            recent_direction = "down"

    lookback = min(30, len(df)-1)
    prev_window = df.iloc[-lookback:-5] if lookback > 5 else df.iloc[:-5]
    prev_high_max = prev_window["high"].max() if len(prev_window) else high.iloc[-6]
    swing_fail = bool((close.iloc[-1] < ema20.iloc[-1]) and (high.iloc[-1] < prev_high_max))

    # setdefault เพื่อไม่ทับค่าที่ logic เดิมอาจใส่มาแล้ว
    cur.setdefault("ema20_slope", ema20_slope)
    cur.setdefault("atr_pct", atr_pct)
    cur.setdefault("recent_direction", recent_direction)
    cur.setdefault("swing_fail", swing_fail)
    cur.setdefault("direction", cur.get("direction", recent_direction))

    det["current"] = cur
    return det

def map_kind(det: dict) -> str:
    """
    ตัดสิน kind (IMPULSE_TOP / IMPULSE_PROGRESS / CORRECTION / UNKNOWN)
    จากผล pattern+context ของ logic เดิม
    """
    patt = str(det.get("pattern", "")).upper()
    cur  = det.get("current", {}) or {}

    stage       = str(cur.get("stage", "")).upper()
    direction   = str(cur.get("direction", cur.get("recent_direction", "side"))).lower()
    recent_dir  = str(cur.get("recent_direction", direction)).lower()
    completed   = bool(det.get("completed", False))
    conf        = float(cur.get("confidence", 0.0))
    ema_slope   = float(cur.get("ema20_slope", 0.0))
    atr_pct     = float(cur.get("atr_pct", 0.0))
    swing_fail  = bool(cur.get("swing_fail", False))

    # Unknown/Diagonal → ยกตาม context เมื่อมั่นใจ/สภาพแวดล้อมบ่งชี้
    if patt in {"UNKNOWN", "DIAGONAL"}:
        if conf >= 0.55:
            return "CORRECTION" if recent_dir == "down" else "IMPULSE_PROGRESS"
        if atr_pct < 0.005 and abs(ema_slope) < 5e-4:
            return "CORRECTION"
        return "UNKNOWN"

    # CORRECTION family
    if "CORRECTION" in stage or "WXY" in stage or patt in {"DOUBLE_THREE","ZIGZAG","FLAT","TRIANGLE","CORRECTION"}:
        return "CORRECTION"

    # IMPULSE family
    if "IMPULSE" in patt or "IMPULSE" in stage or "W5" in stage:
        if completed or "TOP" in stage:
            return "IMPULSE_TOP"
        if swing_fail or (ema_slope <= 0 and recent_dir == "down"):
            return "IMPULSE_TOP"
        if ema_slope > 0 and recent_dir == "up" and conf >= 0.50:
            return "IMPULSE_PROGRESS"
        if ema_slope > -2e-4 and atr_pct >= 0.004:
            return "IMPULSE_PROGRESS"
        return "IMPULSE_TOP"

    # กรณีอื่น ๆ ใช้ ATR+EMA ช่วย
    if atr_pct < 0.005 and abs(ema_slope) < 5e-4:
        return "CORRECTION"

    return "UNKNOWN"

# -------------------- Wrapper (ใหม่) --------------------
def classify_elliott_with_kind(df: pd.DataFrame) -> dict:
    """
    เรียกใช้ classify_elliott(df) เดิม → enrich_context → map_kind → คืน dict เสริม key 'kind'
    """
    # เรียก logic เดิม (ต้องมีอยู่ในไฟล์นี้อยู่แล้ว)
    out = classify_elliott(df)  # <-- ใช้ของเดิม
    if not isinstance(out, dict):
        out = {"pattern": "UNKNOWN", "completed": False, "current": {}}

    out = enrich_context(df, out)
    kind = map_kind(out)
    out["kind"] = kind
    return out
