# app/logic/elliott_logic.py
# ============================================================
# Logic layer: เสริม "สมอง" สำหรับจัดหมวด kind ของ Elliott
# - enrich_context: คำนวณ EMA slope, ATR%, recent_direction, swing_fail
# - map_kind: แปลงผล pattern + context → kind (IMPULSE_TOP / IMPULSE_PROGRESS / CORRECTION / UNKNOWN)
# - classify_elliott_with_kind: wrapper ที่เรียก base classify → enrich → map_kind
# - classify_elliott: Public API (ให้ tests import) คืนโครงสร้างเดียวกัน
# - _call_base_classify: ตัวเรียกใช้งาน classify_elliott (ถ้ามี) หรือ fallback ไป analysis layer
# ============================================================

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Optional
import pandas as pd

__all__ = [
    "classify_elliott",
    "classify_elliott_with_kind",
    "enrich_context",
    "map_kind",
]

# -------------------- Utilities --------------------
def _coerce_to_df(
    data: Any,
    *,
    high_key: str = "high",
    low_key: str = "low",
    close_key: str = "close",
    date_key: Optional[str] = "date",
) -> pd.DataFrame:
    """
    แปลง input ให้เป็น DataFrame ที่มีคอลัมน์อย่างน้อย: high/low/close
    รองรับรูปแบบ:
      - pandas.DataFrame ที่มีคอลัมน์ตรงชื่อ
      - Mapping[str, Sequence] เช่น {"high":[...], "low":[...], "close":[...]}
      - Sequence[float] → จะ map เป็น close ล้วน (mock high/low จาก close)
    """
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif isinstance(data, Mapping):
        df = pd.DataFrame(data)
    elif isinstance(data, Sequence):
        df = pd.DataFrame({close_key: list(data)})
    else:
        raise TypeError("Unsupported input type for Elliott classification")

    # Normalization ชื่อคอลัมน์
    cols_lower = {c.lower(): c for c in df.columns}
    def _ensure_col(name: str):
        if name in df.columns:
            return
        for cand in (name.lower(), name.upper(), name.capitalize()):
            if cand in cols_lower:
                df[name] = df[cols_lower[cand]]
                return

    _ensure_col(high_key)
    _ensure_col(low_key)
    _ensure_col(close_key)

    # ถ้ายังไม่มี high/low ให้ mock จาก close
    if high_key not in df.columns and close_key in df.columns:
        df[high_key] = df[close_key]
    if low_key not in df.columns and close_key in df.columns:
        df[low_key] = df[close_key]

    # ตรวจขั้นต่ำ
    needed = {high_key, low_key, close_key}
    if not needed.issubset(df.columns):
        raise ValueError(f"Missing columns for Elliott classification: need {needed}, got {list(df.columns)}")

    # sort by date ถ้ามี
    dk = date_key if date_key and date_key in df.columns else None
    if dk:
        df = df.sort_values(dk).reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    # ตัดข้อมูลให้ไม่เกิน 600 แท่ง เพื่อความเร็ว
    if len(df) > 600:
        df = df.tail(600).reset_index(drop=True)
    return df


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
    พยายามใช้ classify_elliott (ถ้ามีในสโคปปัจจุบัน); ถ้าไม่มีก็ fallback ไป analysis layer
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
    - ema20_slope  : ค่าชัน EMA20 (อัตราส่วนระหว่างแท่งปัจจุบันกับ 5 แท่งก่อน)
    - atr_pct      : ATR เทียบกับ close
    - recent_direction : up/down/side จากการเปรียบเทียบ 5 แท่ง
    - swing_fail   : อยู่ใต้ EMA20 และทำ Lower High เมื่อเทียบกับ high ย้อนหลัง
    """
    if not isinstance(det, dict):
        return det
    cur = det.get("current", {}) or {}

    # ---------- เคสข้อมูลน้อย: ใส่ค่าพื้นฐานให้ครบเพื่อกัน KeyError ----------
    if df_ctx is None or len(df_ctx) < 25:
        direction = "side"
        try:
            if df_ctx is not None and "close" in df_ctx.columns and len(df_ctx) >= 2:
                c0 = float(df_ctx["close"].iloc[0])
                c1 = float(df_ctx["close"].iloc[-1])
                if c0 != 0:
                    pct = (c1 - c0) / abs(c0)
                    if pct > 0.002:
                        direction = "up"
                    elif pct < -0.002:
                        direction = "down"
        except Exception:
            pass

        cur.setdefault("ema20_slope", 0.0)
        cur.setdefault("atr_pct", 0.0)
        cur.setdefault("recent_direction", direction)
        cur.setdefault("swing_fail", False)
        cur.setdefault("direction", cur.get("direction", direction))

        det["current"] = cur
        return det

    # ---------- เคสข้อมูลพอ: คำนวณเต็ม ----------
    df = df_ctx.sort_values("date").tail(120).reset_index(drop=True) if "date" in df_ctx.columns \
         else df_ctx.tail(120).reset_index(drop=True)
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
    prev_high_max = prev_window["high"].max() if len(prev_window) else (high.iloc[-6] if len(high) >= 6 else high.iloc[-1])
    swing_fail = bool((close.iloc[-1] < ema20.iloc[-1]) and (high.iloc[-1] < prev_high_max))

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
    conf        = float(cur.get("confidence", 0.0)) if "confidence" in cur else 0.0
    ema_slope   = float(cur.get("ema20_slope", 0.0))
    atr_pct     = float(cur.get("atr_pct", 0.0))
    swing_fail  = bool(cur.get("swing_fail", False))

    # ---------- UNKNOWN / DIAGONAL ----------
    if patt in {"UNKNOWN", "DIAGONAL"}:
        slope_abs = abs(ema_slope)

        if conf >= 0.55:
            return "CORRECTION" if recent_dir == "down" else "IMPULSE_PROGRESS"

        if ema_slope >= 0.01 and recent_dir == "up":
            return "IMPULSE_PROGRESS"
        if ema_slope <= -0.01 and recent_dir == "down":
            return "CORRECTION"

        if swing_fail and recent_dir != "up":
            return "IMPULSE_TOP"

        if atr_pct >= 0.02 and slope_abs >= 0.005:
            return "IMPULSE_PROGRESS" if recent_dir == "up" else "CORRECTION"

        if atr_pct < 0.005 and slope_abs < 5e-4:
            return "CORRECTION"

        return "UNKNOWN"

    # ---------- CORRECTION family ----------
    if "CORRECTION" in stage or "WXY" in stage or patt in {"DOUBLE_THREE", "ZIGZAG", "FLAT", "TRIANGLE", "CORRECTION"}:
        return "CORRECTION"

    # ---------- IMPULSE family ----------
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


def classify_elliott(data: Any) -> Dict[str, Any]:
    """
    Public API ที่ tests จะ import:
      - รับข้อมูลได้หลากหลาย → แปลงเป็น DataFrame
      - คืน dict ที่มี key 'kind' เสมอ
    """
    df = _coerce_to_df(data)
    return classify_elliott_with_kind(df)
