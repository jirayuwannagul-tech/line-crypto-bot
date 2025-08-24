# app/analysis/dow.py
# -----------------------------------------------------------------------------
# Dow Theory — RULES ONLY
# ตรวจสอบแนวโน้มตาม "กฎดั้งเดิม" ของ Dow Theory ด้วยสวิง High/Low เท่านั้น
# ไม่มี EMA, ไม่มีโหวต, ไม่มี confidence, ไม่มีตัวกรองช่วงราคา
#
# Output:
# {
#   "trend": "UP" | "DOWN" | "SIDE",
#   "rules": [
#       {"name": "...", "passed": True/False, "details": {...}},
#       ...
#   ],
#   "debug": {
#       "swings": [...],          # สวิงล่าสุด (idx, price, type)
#       "used_indices": [...],    # index ของสวิงที่นำมาตัดสิน
#       "used_types": [...],      # H/L
#       "used_prices": [...]
#   }
# }
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Dict, Literal, Tuple, List
import pandas as pd
import numpy as np

Trend = Literal["UP", "DOWN", "SIDE"]

__all__ = ["analyze_dow_rules", "Trend"]

# -----------------------------------------------------------------------------
# Utilities: หา swing highs/lows ด้วย fractals อย่างง่าย
# -----------------------------------------------------------------------------
def _pivots(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    """
    คืนค่า (is_swing_high, is_swing_low) เป็น Series ของ boolean
    ใช้วิธี fractal windows: จุดกลางสูง/ต่ำสุดเมื่อเทียบซ้าย/ขวา
    """
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
    """
    สร้าง DataFrame ของสวิงเรียงตามเวลา: ['idx','price','type'] โดย type ∈ {'H','L'}
    บังคับให้สลับ H/L ถ้าชนกันติดกันจะเก็บค่าที่สุดโต่งกว่า
    """
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
            # เก็บที่ "สุดโต่งกว่า"
            if r["type"] == "H":
                if r["price"] >= cleaned[-1]["price"]:
                    cleaned[-1] = r
            else:  # "L"
                if r["price"] <= cleaned[-1]["price"]:
                    cleaned[-1] = r
        else:
            cleaned.append(r)
    return pd.DataFrame(cleaned)


# -----------------------------------------------------------------------------
# Core: Dow Theory RULES
# -----------------------------------------------------------------------------
def _extract_recent_sequence(sw: pd.DataFrame, need_points: int = 6) -> pd.DataFrame:
    """
    ดึงลำดับสวิงล่าสุดอย่างน้อย 6 จุด (H/L สลับกัน) สำหรับตรวจ HH/HL หรือ LH/LL
    ถ้ามากพอจะคืน tail(need_points) มิฉะนั้นคืนทั้งชุด
    """
    if len(sw) == 0:
        return sw
    # ให้แน่ใจว่าส่วนท้ายสลับ H/L
    tail = sw.tail(max(need_points, 3)).reset_index(drop=True)
    # ถ้าไม่สลับ ให้เลื่อนหน้าต่างกว้างขึ้นเล็กน้อย (เผื่อกรณีพลาดนิดหน่อย)
    if len(tail) >= 3:
        types = tail["type"].tolist()
        ok_alt = all(types[i] != types[i+1] for i in range(len(types)-1))
        if not ok_alt and len(sw) > len(tail):
            tail = sw.tail(min(len(sw), max(need_points+2, 8))).reset_index(drop=True)
    return tail


def _dow_rules_decision(win: pd.DataFrame) -> Dict[str, object]:
    """
    ตัดสินแนวโน้มตามกฎ Dow:
      - Uptrend: มี Higher High (HH) และ Higher Low (HL) ต่อเนื่อง (ล่าสุด > ก่อนหน้า)
      - Downtrend: มี Lower High (LH) และ Lower Low (LL) ต่อเนื่อง (ล่าสุด < ก่อนหน้า)
      - ไม่ชัด → SIDE
    ใช้เฉพาะการเทียบ "จุดสูงสุด" และ "จุดต่ำสุด" ล่าสุดกับจุดก่อนหน้า (ไม่มีตัวช่วยอื่น)
    """
    rules = []

    # แยก highs/lows ตามลำดับเวลา
    highs = [r["price"] for r in win.to_dict("records") if r["type"] == "H"]
    lows  = [r["price"] for r in win.to_dict("records") if r["type"] == "L"]

    # ต้องมีอย่างน้อย 2 high และ 2 low เพื่อเทียบก่อน-หลัง
    hh_present = len(highs) >= 2 and highs[-1] > highs[-2]
    hl_present = len(lows)  >= 2 and lows[-1]  > lows[-2]
    lh_present = len(highs) >= 2 and highs[-1] < highs[-2]
    ll_present = len(lows)  >= 2 and lows[-1]  < lows[-2]

    rules.append({"name": "Higher High (HH)", "passed": bool(hh_present), "details": {"last_H": highs[-1] if len(highs)>=1 else None, "prev_H": highs[-2] if len(highs)>=2 else None}})
    rules.append({"name": "Higher Low (HL)",  "passed": bool(hl_present), "details": {"last_L": lows[-1]  if len(lows)>=1  else None, "prev_L": lows[-2]  if len(lows)>=2  else None}})
    rules.append({"name": "Lower High (LH)",  "passed": bool(lh_present), "details": {"last_H": highs[-1] if len(highs)>=1 else None, "prev_H": highs[-2] if len(highs)>=2 else None}})
    rules.append({"name": "Lower Low (LL)",   "passed": bool(ll_present), "details": {"last_L": lows[-1]  if len(lows)>=1  else None, "prev_L": lows[-2]  if len(lows)>=2  else None}})

    # กฎการตัดสินแนวโน้ม (ดั้งเดิม):
    # - ขาขึ้น: ต้องมี HH และ HL (พร้อมกัน)
    # - ขาลง: ต้องมี LH และ LL (พร้อมกัน)
    # - อย่างอื่น → SIDE
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
    """
    ตรวจแนวโน้มตามกฎ Dow Theory "ล้วน ๆ" จาก OHLC DataFrame
    ต้องมีคอลัมน์อย่างน้อย: ['high','low','close']
    """
    needed = {"high", "low", "close"}
    if not needed.issubset(df.columns):
        return {
            "trend": "SIDE",
            "rules": [{"name": "missing_columns", "passed": False, "details": {"columns": list(df.columns)}}],
            "debug": {},
        }

    sw = _build_swings(df, left=pivot_left, right=pivot_right)
    if len(sw) < 4:  # ต้องการอย่างน้อย H/L อย่างละ 2 ครั้งเพื่อเทียบก่อน-หลัง
        return {
            "trend": "SIDE",
            "rules": [{"name": "insufficient_swings", "passed": False, "details": {"swings": len(sw)}}],
            "debug": {"swings": sw.to_dict("records")},
        }

    if len(sw) > max_swings:
        sw = sw.tail(max_swings).reset_index(drop=True)

    win = _extract_recent_sequence(sw, need_points=6)
    trend, rules = _dow_rules_decision(win)

    return {
        "trend": trend,
        "rules": rules,
        "debug": {
            "swings": sw.tail(12).to_dict("records"),
            "used_indices": win["idx"].tolist(),
            "used_types": win["type"].tolist(),
            "used_prices": win["price"].tolist(),
        },
    }
