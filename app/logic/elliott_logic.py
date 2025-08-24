# app/logic/elliott_logic.py
# ============================================================
# Logic layer: เสริม "สมอง" สำหรับจัดหมวด kind ของ Elliott
# - enrich_context: คำนวณ EMA slope, ATR%, recent_direction, swing_fail
# - map_kind: แปลงผล pattern + context → kind (IMPULSE_TOP / IMPULSE_PROGRESS / CORRECTION / UNKNOWN)
# - classify_elliott_with_kind: wrapper ที่เรียก base classify → enrich → map_kind
# - _call_base_classify: ตัวเรียกใช้งาน classify_elliott (ถ้ามี) หรือ fallback ไป analysis layer
# ============================================================

from __future__ import annotations

import math
import pandas as pd
from typing import Any, Dict

# ------------------------------------------------------------
# NOTE:
# ถ้ามีฟังก์ชัน classify_elliott อยู่ในไฟล์นี้หรือถูก import ไว้ก่อนหน้า
# _call_base_classify จะเรียกใช้อันนั้นโดยตรง
# ถ้าไม่มี → จะ fallback ไปใช้ app.analysis.elliott (rules layer)
# ------------------------------------------------------------

# -------------------- Indicators --------------------
def _ema(series: pd.Series, span: int = 20) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

# -------------------- Base classify resolver --------------------
def _call_base_classify(df: pd.DataFrame) -> Dict[str, Any]:
    """
    พยายามใช้ classify_elliott (ถ้ามี); ถ้าไม่มีก็ fallback ไป analysis layer
    คืนโครงสร้างมาตรฐานแบบ dict
    """
    # 1) ใช้ classify_elliott จากสโคปปัจจุบัน (ถ้ามี)
    try:
        base_fn = classify_elliott  # type: ignore[name-defined]
    except NameError:
        base_fn = None

    if callable(base_fn):
        try:
            out = base_fn(df)  # type: ignore[misc]
            if isinstance(out, dict):
                return out
        except Exception:
            pass  # ให้ fallback ต่อด้านล่าง

    # 2) Fallback: ใช้ rules ใน analysis layer
    try:
        from app.analysis import elliott as ew  # import ภายในเพื่อหลีกเลี่ยงวงจรอิมพอร์ต
        raw = None
        if hasattr(ew, "analyze_elliott"):
            raw = ew.analyze_elliott(df, min_swing_pct=3.0, strict_impulse=True, allow_overlap=False)
        elif hasattr(ew, "analyze_elliott_rules"):
            raw = ew.analyze_elliott_rules(df, min_swing_pct=3.0, strict_impulse=True, allow_overlap=False)

        if isinstance(raw, dict):
            return {
                "pattern": raw.get("pattern", raw.get("label", "UNKNOWN")),
                "completed": bool(raw.get("completed", False)),
                "current": raw.get("current", {}) or {},
                "rules": raw.get("rules", []),
                "debug": raw.get("debug", {}),
            }
    except Exception:
        pass

    # 3) สุดท้ายจริง ๆ
    return {"pattern": "UNKNOWN", "completed": False, "current": {}, "rules": [], "debug": {}}

# -------------------- Context enrichment --------------------
def enrich_context(df_ctx: pd.DataFrame, det: Dict[str, Any]) -> Dict[str, Any]:
    """
    เติมข้อมูล context ลง det['current']:
    - ema20_slope  : ค่าชัน EMA20 (อัตราส่วน 5 แท่ง)
    - atr_pct      : ATR เทียบกับ close
    - recent_direction : up/down/side จากการเปรียบเทียบ 5 แท่ง
    - swing_fail   : อยู่ใต้ EMA20 และทำ Lower High เมื่อเทียบกับ high ย้อนหลัง
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
    denom = base if base != 0 else 1e-9
    ema20_slope = float((ema20.iloc[-1] - base) / denom)

    atr14 = _atr(df, 14)
    last_close = close.iloc[-1] if len(close) else 1e-9
    atr_pct = float(atr14.iloc[-1] / (last_close if last_close != 0 else 1e-9))

    recent_direction = "side"
    if len(close) >= 6:
        if close.iloc[-1] > close.iloc[-5] * 1.002:
            recent_direction = "up"
        elif close.iloc[-1] < close.iloc[-5] * 0.998:
            recent_direction = "down"

    lookback = min(30, len(df)-1)
    prev_window = df.iloc[-lookback:-5] if lookback > 5 else df.iloc[:-5]
    prev_high_max = prev_window["high"].max() if len(prev_window) else high.iloc[-6] if len(high) >= 6 else high.iloc[-1]
    swing_fail = bool((close.iloc[-1] < ema20.iloc[-1]) and (high.iloc[-1] < prev_high_max))

    # setdefault เพื่อไม่ทับค่าที่ logic เดิมอาจใส่มาแล้ว
    cur.setdefault("ema20_slope", ema20_slope)
    cur.setdefault("atr_pct", atr_pct)
    cur.setdefault("recent_direction", recent_direction)
    cur.setdefault("swing_fail", swing_fail)
    cur.setdefault("direction", cur.get("direction", recent_direction))

    det["current"] = cur
    return det

# -------------------- Mapping to "kind" --------------------
def map_kind(det: Dict[str, Any]) -> str:
    """
    ตัดสิน kind (IMPULSE_TOP / IMPULSE_PROGRESS / CORRECTION / UNKNOWN)
    จากผล pattern + context ของ logic เดิม
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

    # UNKNOWN/DIAGONAL → ยกตาม context เมื่อมั่นใจ/สภาพแวดล้อมบ่งชี้
    if patt in {"UNKNOWN", "DIAGONAL"}:
        if conf >= 0.55:
            return "CORRECTION" if recent_dir == "down" else "IMPULSE_PROGRESS"
        if atr_pct < 0.005 and abs(ema_slope) < 5e-4:
            return "CORRECTION"
        return "UNKNOWN"

    # CORRECTION family
    if "CORRECTION" in stage or "WXY" in stage or patt in {"DOUBLE_THREE", "ZIGZAG", "FLAT", "TRIANGLE", "CORRECTION"}:
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

# -------------------- Public API --------------------
def classify_elliott_with_kind(df: pd.DataFrame) -> Dict[str, Any]:
    """
    เรียก base classify (ถ้ามี) หรือ fallback → enrich_context → map_kind → เพิ่ม key 'kind'
    """
    out = _call_base_classify(df)
    if not isinstance(out, dict):
        out = {"pattern": "UNKNOWN", "completed": False, "current": {}}

    out = enrich_context(df, out)
    kind = map_kind(out)
    out["kind"] = kind
    return out
