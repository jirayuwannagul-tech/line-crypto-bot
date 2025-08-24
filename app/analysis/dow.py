# app/analysis/dow.py
# -----------------------------------------------------------------------------
# Dow Theory — RULES ONLY
# ตรวจสอบแนวโน้มตาม "กฎดั้งเดิม" ของ Dow Theory ด้วยสวิง High/Low เท่านั้น
# ไม่มี EMA, ไม่มีตัวชี้วัดอื่น
#
# Public API:
#   - analyze_dow(data, *, pivot_left=2, pivot_right=2, max_swings=30) -> dict
#       รองรับ input ได้ทั้ง DataFrame, Mapping[str, Sequence], หรือ Sequence[float]
#       คืนโครงสร้าง:
#         {
#           "trend": "UP" | "DOWN" | "SIDE",
#           "trend_primary": "UP" | "DOWN" | "SIDE",   # ✅ เพิ่ม key นี้
#           "rules": [...],
#           "debug": {...}
#         }
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, Literal, Tuple, List, Mapping, Sequence, Optional
import numpy as np
import pandas as pd

Trend = Literal["UP", "DOWN", "SIDE"]

__all__ = ["analyze_dow", "analyze_dow_rules", "Trend"]

# -----------------------------------------------------------------------------
# Coercion: แปลง input ให้เป็น DataFrame ที่มีคอลัมน์อย่างน้อย: high/low/close
# -----------------------------------------------------------------------------
def _coerce_to_df(
    data: Any,
    *,
    high_key: str = "high",
    low_key: str = "low",
    close_key: str = "close",
    date_key: Optional[str] = "date",
) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif isinstance(data, Mapping):
        df = pd.DataFrame(data)
    elif isinstance(data, Sequence):
        df = pd.DataFrame({close_key: list(data)})
    else:
        raise TypeError("Unsupported input type for Dow analysis")

    # เติม/แมปชื่อคีย์ให้ครบ
    cols = {c.lower(): c for c in df.columns}
    def _ensure_col(name: str):
        if name in df.columns:
            return
        cand = None
        for alt in (name.lower(), name.upper(), name.capitalize()):
            if alt in cols:
                cand = cols[alt]; break
        if cand is not None:
            df[name] = df[cand]

    _ensure_col(high_key)
    _ensure_col(low_key)
    _ensure_col(close_key)

    # ถ้าไม่มี high/low ให้ mock จาก close
    if high_key not in df.columns and close_key in df.columns:
        df[high_key] = df[close_key]
    if low_key not in df.columns and close_key in df.columns:
        df[low_key] = df[close_key]

    needed = {high_key, low_key, close_key}
    if not needed.issubset(df.columns):
        raise ValueError(f"Missing columns for Dow analysis: need {needed}, got {list(df.columns)}")

    # sort by date ถ้ามี
    dk = date_key if date_key and date_key in df.columns else None
    if dk:
        df = df.sort_values(dk).reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    # ตัดข้อมูลเพื่อความเร็ว
    if len(df) > 1000:
        df = df.tail(1000).reset_index(drop=True)
    return df


# -----------------------------------------------------------------------------
# Utilities: หา swing highs/lows ด้วย fractals อย่างง่าย
# -----------------------------------------------------------------------------
def _pivots(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    n = len(df)
    if n == 0:
        return pd.Series(dtype=bool, index=df.index), pd.Series(dtype=bool, index=df.index)

    high = df["high"].values
    low = df["low"].values
    swing_high = np.full(n, False)
    swing_low = np.full(n, False)

    for i in range(left, n - right):
        win_h = high[i-left:i+right+1]
        win_l = low[i-left:i+right+1]

        if high[i] == win_h.max() and np.argmax(win_h) == left:
            swing_high[i] = True
        if low[i] == win_l.min() and np.argmin(win_l) == left:
            swing_low[i] = True

    return pd.Series(swing_high, index=df.index), pd.Series(swing_low, index=df.index)


def _build_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    is_sh, is_sl = _pivots(df, left=left, right=right)
    rows: List[Dict[str, object]] = []
    for i in range(len(df)):
        if bool(is_sh.iat[i]):
            rows.append({"idx": i, "price": float(df["high"].iat[i]), "type": "H"})
        if bool(is_sl.iat[i]):
            rows.append({"idx": i, "price": float(df["low"].iat[i]), "type": "L"})

    if not rows:
        return pd.DataFrame(columns=["idx", "price", "type"])

    sw = pd.DataFrame(rows).sort_values("idx").reset_index(drop=True)

    cleaned: List[Dict[str, object]] = []
    for r in sw.to_dict("records"):
        if not cleaned:
            cleaned.append(r); continue
        if cleaned[-1]["type"] == r["type"]:
            if r["type"] == "H":
                if r["price"] >= cleaned[-1]["price"]:
                    cleaned[-1] = r
            else:
                if r["price"] <= cleaned[-1]["price"]:
                    cleaned[-1] = r
        else:
            cleaned.append(r)
    return pd.DataFrame(cleaned)


# -----------------------------------------------------------------------------
# Core: Dow Theory RULES
# -----------------------------------------------------------------------------
def _extract_recent_sequence(sw: pd.DataFrame, need_points: int = 6) -> pd.DataFrame:
    if len(sw) == 0:
        return sw
    tail = sw.tail(max(need_points, 3)).reset_index(drop=True)
    if len(tail) >= 3:
        types = tail["type"].tolist()
        ok_alt = all(types[i] != types[i+1] for i in range(len(types)-1))
        if not ok_alt and len(sw) > len(tail):
            tail = sw.tail(min(len(sw), max(need_points+2, 8))).reset_index(drop=True)
    return tail


def _dow_rules_decision(win: pd.DataFrame) -> Tuple[Trend, List[Dict[str, object]]]:
    rules: List[Dict[str, object]] = []

    highs = [r["price"] for r in win.to_dict("records") if r["type"] == "H"]
    lows  = [r["price"] for r in win.to_dict("records") if r["type"] == "L"]

    hh_present = len(highs) >= 2 and highs[-1] > highs[-2]
    hl_present = len(lows)  >= 2 and lows[-1]  > lows[-2]
    lh_present = len(highs) >= 2 and highs[-1] < highs[-2]
    ll_present = len(lows)  >= 2 and lows[-1]  < lows[-2]

    rules.append({"name": "Higher High (HH)", "passed": bool(hh_present),
                  "details": {"last_H": highs[-1] if len(highs)>=1 else None,
                              "prev_H": highs[-2] if len(highs)>=2 else None}})
    rules.append({"name": "Higher Low (HL)", "passed": bool(hl_present),
                  "details": {"last_L": lows[-1] if len(lows)>=1 else None,
                              "prev_L": lows[-2] if len(lows)>=2 else None}})
    rules.append({"name": "Lower High (LH)", "passed": bool(lh_present),
                  "details": {"last_H": highs[-1] if len(highs)>=1 else None,
                              "prev_H": highs[-2] if len(highs)>=2 else None}})
    rules.append({"name": "Lower Low (LL)", "passed": bool(ll_present),
                  "details": {"last_L": lows[-1] if len(lows)>=1 else None,
                              "prev_L": lows[-2] if len(lows)>=2 else None}})

    if hh_present and hl_present:
        trend: Trend = "UP"
    elif lh_present and ll_present:
        trend = "DOWN"
    else:
        trend = "SIDE"

    return trend, rules


# -----------------------------------------------------------------------------
# Public API (RULES ONLY)
# -----------------------------------------------------------------------------
def analyze_dow_rules(
    df: pd.DataFrame,
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
    max_swings: int = 30,
) -> Dict[str, object]:
    needed = {"high", "low", "close"}
    if not needed.issubset(df.columns):
        return {
            "trend": "SIDE",
            "trend_primary": "SIDE",  # ✅ เพิ่ม key สำหรับความเข้ากันได้
            "rules": [{"name": "missing_columns", "passed": False, "details": {"columns": list(df.columns)}}],
            "debug": {},
        }

    sw = _build_swings(df, left=pivot_left, right=pivot_right)
    if len(sw) < 4:
        return {
            "trend": "SIDE",
            "trend_primary": "SIDE",
            "rules": [{"name": "insufficient_swings", "passed": False, "details": {"swings": len(sw)}}],
            "debug": {"swings": sw.to_dict("records")},
        }

    if len(sw) > max_swings:
        sw = sw.tail(max_swings).reset_index(drop=True)

    win = _extract_recent_sequence(sw, need_points=6)
    trend, rules = _dow_rules_decision(win)

    return {
        "trend": trend,
        "trend_primary": trend,  # ✅ เพิ่ม field ที่ test ต้องการ
        "rules": rules,
        "debug": {
            "swings": sw.tail(12).to_dict("records"),
            "used_indices": win["idx"].tolist(),
            "used_types": win["type"].tolist(),
            "used_prices": win["price"].tolist(),
        },
    }


def analyze_dow(
    data: Any,
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
    max_swings: int = 30,
) -> Dict[str, object]:
    df = _coerce_to_df(data)
    return analyze_dow_rules(
        df,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        max_swings=max_swings,
    )
