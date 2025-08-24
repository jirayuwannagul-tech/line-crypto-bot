# app/analysis/patterns.py
# =============================================================================
# Chart Patterns — RULES ONLY
# -----------------------------------------------------------------------------
# ตรวจจับรูปแบบจาก "กฎล้วน ๆ" (ไม่มี heuristic/target/การเดา label)
# Supported:
#   - Elliott (IMPULSE, DIAGONAL) : ตามกฎ 1) W2 ไม่ทับจุดเริ่ม W1, 2) W3 ไม่สั้นสุด, 3) W4 ไม่ overlap W1
#   - Zigzag : B retrace ~38.2–61.8% ของ A, C ทิศเดียวกับ A, |C|≈|A| (±15%) หรือ ≈1.618×|A| (±15%)
#   - Flat   : B retrace ~90–110% ของ A, C ทิศเดียวกับ A, |C|≈|A| (±15%) หรือ ≈1.618×|A| (±15%)
#   - Triangle: 5 ขา A-B-C-D-E สลับชนิด H/L และเป็น Contracting หรือ Expanding อย่างเคร่งครัด
# Output ของแต่ละ detector:
# {
#   "pattern": "IMPULSE|DIAGONAL|ZIGZAG|FLAT|TRIANGLE" | None,
#   "rules": [{"name": "...", "passed": bool, "details": {...}}, ...],
#   "points": [{"idx": int, "price": float, "type": "H|L", "ts": int}, ...],
#   "debug": {...}
# }
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple

try:
    from app.schemas.series import Series  # type: ignore
except Exception:
    from typing import TypedDict
    class Candle(TypedDict, total=False):
        open: float; high: float; low: float; close: float; volume: float; ts: int
    class Series(TypedDict):
        symbol: str
        timeframe: str
        candles: List[Candle]

import numpy as np

# =============================================================================
# Low-level helpers: swings & math
# =============================================================================

def _swing_points(candles: List[Dict[str, Any]], left: int = 3, right: int = 3) -> List[Dict[str, Any]]:
    """
    หา swing high/low ด้วย fractal window อย่างง่าย
    - swing high: high จุดกลาง = ค่าสูงสุดในช่วง [i-left, i+right]
    - swing low : low  จุดกลาง = ค่าต่ำสุดในช่วง [i-left, i+right]
    บังคับให้สลับชนิด H/L; ถ้าชนซ้ำกันให้เก็บจุดที่ 'สุดโต่งกว่า'
    """
    n = len(candles)
    if n == 0:
        return []

    highs = [float(c["high"]) for c in candles]
    lows  = [float(c["low"])  for c in candles]
    rows: List[Dict[str, Any]] = []

    for i in range(left, n - right):
        win_h = highs[i-left:i+right+1]
        win_l = lows[i-left:i+right+1]
        if highs[i] == max(win_h) and np.argmax(win_h) == left:
            rows.append({"idx": i, "type": "H", "price": highs[i], "ts": int(candles[i].get("ts", i))})
        if lows[i] == min(win_l) and np.argmin(win_l) == left:
            rows.append({"idx": i, "type": "L", "price": lows[i],  "ts": int(candles[i].get("ts", i))})

    if not rows:
        return []

    rows.sort(key=lambda r: r["idx"])
    cleaned: List[Dict[str, Any]] = []
    for r in rows:
        if not cleaned:
            cleaned.append(r); continue
        if cleaned[-1]["type"] == r["type"]:
            # เก็บจุดที่ 'สุดโต่งกว่า'
            if r["type"] == "H":
                if r["price"] >= cleaned[-1]["price"]:
                    cleaned[-1] = r
            else:  # "L"
                if r["price"] <= cleaned[-1]["price"]:
                    cleaned[-1] = r
        else:
            cleaned.append(r)
    return cleaned


def _leg_len(a: float, b: float) -> float:
    return abs(b - a)

def _dir(a: float, b: float) -> str:
    if b > a: return "up"
    if b < a: return "down"
    return "side"

def _retracement_ratio(a0: float, a1: float, b: float) -> Optional[float]:
    """
    Retracement ของขา A (a0->a1) โดยจุด b:
      - ถ้า A ขึ้น: (a1 - b) / (a1 - a0)
      - ถ้า A ลง : (b - a1) / (a0 - a1)
    """
    if a1 == a0: return None
    if a1 > a0:  # up
        return (a1 - b) / (a1 - a0)
    else:        # down
        return (b - a1) / (a0 - a1)

def _ratio(val: float, base: float) -> Optional[float]:
    if base == 0: return None
    return abs(val) / abs(base)

# =============================================================================
# RULE DETECTORS (no heuristics/targets)
# =============================================================================

def detect_elliott_rules(series: Series, *, window_points: int = 6, lookback_pivot: int = 3) -> Dict[str, Any]:
    """
    ตรวจ Elliott "กฎล้วน ๆ" สำหรับ Impulse หรือ Diagonal:
      - ต้องได้สวิง 6 จุดล่าสุดชนิดสลับกันแบบ L-H-L-H-L-H (แนวโน้มขึ้น) หรือ H-L-H-L-H-L (ลง)
      - Rule #1: Wave2 ไม่ retrace ทะลุจุดเริ่ม Wave1
      - Rule #2: Wave3 ไม่ใช่คลื่นสั้นสุดใน (1,3,5)
      - Rule #3: Wave4 ไม่ overlap เขต Wave1 (หาก overlap แต่ข้ออื่นผ่าน -> DIAGONAL)
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < window_points:
        return {"pattern": None, "rules": [], "points": []}

    win = swings[-window_points:]
    types = [p["type"] for p in win]
    prices = [p["price"] for p in win]

    if types not in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
        return {"pattern": None, "rules": [], "points": []}

    direction = "up" if types[-1] == "H" else "down"
    p0, p1, p2, p3, p4, p5 = prices
    w1 = _leg_len(p0, p1)
    w3 = _leg_len(p2, p3)
    w5 = _leg_len(p4, p5)

    rules = []

    # Rule 1: Wave2 ไม่เลยจุดเริ่ม W1
    r1_ok = (p2 > p0) if direction == "up" else (p2 < p0)
    rules.append({"name": "W2 not beyond W1 start", "passed": bool(r1_ok), "details": {"p0": p0, "p2": p2, "dir": direction}})

    # Rule 2: W3 ไม่สั้นสุด
    shortest = min(w1, w3, w5)
    r2_ok = (w3 > shortest) or (w3 == shortest and not (w3 == w1 == w5))
    rules.append({"name": "W3 not the shortest (1,3,5)", "passed": bool(r2_ok), "details": {"w1": w1, "w3": w3, "w5": w5}})

    # Rule 3: W4 ไม่ overlap เขต W1
    if direction == "up":
        r3_ok = (win[4]["price"] > win[1]["price"])  # p4 > p1
    else:
        r3_ok = (win[4]["price"] < win[1]["price"])  # p4 < p1
    rules.append({"name": "W4 no overlap W1", "passed": bool(r3_ok), "details": {"p1": p1, "p4": p4, "dir": direction}})

    # ตัดสิน pattern จากกฎ
    if all(r["passed"] for r in rules):
        patt = "IMPULSE"
    elif (not r3_ok) and r1_ok and r2_ok:
        patt = "DIAGONAL"
    else:
        patt = None

    return {"pattern": patt, "rules": rules, "points": win, "debug": {"types": types, "prices": prices}}


def detect_zigzag_rules(series: Series, *, lookback_pivot: int = 3) -> Dict[str, Any]:
    """
    Zigzag rules:
      - ใช้ 4 จุดล่าสุด: ต้องเป็น H-L-H-L หรือ L-H-L-H
      - B retrace(A) ∈ [0.382, 0.618]
      - C ทิศเดียวกับ A
      - |C|≈|A| (±15%) หรือ |C|≈1.618×|A| (±15%)
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < 4:
        return {"pattern": None, "rules": [], "points": []}

    win = swings[-4:]
    types = [p["type"] for p in win]
    prices = [p["price"] for p in win]

    if types not in (["H","L","H","L"], ["L","H","L","H"]):
        return {"pattern": None, "rules": [], "points": []}

    p0, p1, p2, p3 = prices
    dir_A = _dir(p0, p1)
    rules = []

    # Rule 1: B retracement in [0.382, 0.618]
    rB = _retracement_ratio(p0, p1, p2)
    r1_ok = (rB is not None) and (0.382 <= rB <= 0.618)
    rules.append({"name": "B retraces 38.2%–61.8% of A", "passed": bool(r1_ok), "details": {"B_retrace": float(rB) if rB is not None else None}})

    # Rule 2: C same direction as A
    r2_ok = (_dir(p2, p3) == dir_A)
    rules.append({"name": "C same direction as A", "passed": bool(r2_ok), "details": {"dir_A": dir_A, "dir_C": _dir(p2, p3)}})

    # Rule 3: |C|≈|A| (±15%) OR ≈1.618×|A| (±15%)
    A_len = _leg_len(p0, p1)
    C_len = _leg_len(p2, p3)
    ratio_CA = _ratio(C_len, A_len) or 0.0
    close_to_1 = 0.85 <= ratio_CA <= 1.15
    close_to_1618 = (1.618 * 0.85) <= ratio_CA <= (1.618 * 1.15)
    r3_ok = close_to_1 or close_to_1618
    rules.append({"name": "|C| ≈ |A| or ≈1.618×|A| (±15%)", "passed": bool(r3_ok), "details": {"|A|": A_len, "|C|": C_len, "C/A": ratio_CA}})

    patt = "ZIGZAG" if all(r["passed"] for r in rules) else None
    return {"pattern": patt, "rules": rules, "points": win, "debug": {"types": types, "prices": prices}}


def detect_flat_rules(series: Series, *, lookback_pivot: int = 3) -> Dict[str, Any]:
    """
    Flat rules:
      - ใช้ 4 จุดล่าสุด: ต้องเป็น H-L-H-L หรือ L-H-L-H
      - B retrace(A) ~ 90%–110%
      - C ทิศเดียวกับ A
      - |C|≈|A| (±15%) OR ≈1.618×|A| (±15%) (Expanded Flat)
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < 4:
        return {"pattern": None, "rules": [], "points": []}

    win = swings[-4:]
    types = [p["type"] for p in win]
    prices = [p["price"] for p in win]
    if types not in (["H","L","H","L"], ["L","H","L","H"]):
        return {"pattern": None, "rules": [], "points": []}

    p0, p1, p2, p3 = prices
    dir_A = _dir(p0, p1)
    rules = []

    # Rule 1: B retrace ~90%–110% ของ A
    rB = _retracement_ratio(p0, p1, p2)
    r1_ok = (rB is not None) and (0.90 <= rB <= 1.10)
    rules.append({"name": "B retraces ~90%–110% of A", "passed": bool(r1_ok), "details": {"B_retrace": float(rB) if rB is not None else None}})

    # Rule 2: C ทิศเดียวกับ A
    r2_ok = (_dir(p2, p3) == dir_A)
    rules.append({"name": "C same direction as A", "passed": bool(r2_ok), "details": {"dir_A": dir_A, "dir_C": _dir(p2, p3)}})

    # Rule 3: |C|≈|A| (±15%) OR ≈1.618×|A| (±15%)
    A_len = _leg_len(p0, p1)
    C_len = _leg_len(p2, p3)
    ratio_CA = _ratio(C_len, A_len) or 0.0
    r3_ok = (0.85 <= ratio_CA <= 1.15) or ((1.618 * 0.85) <= ratio_CA <= (1.618 * 1.15))
    rules.append({"name": "|C| ≈ |A| or ≈1.618×|A| (±15%)", "passed": bool(r3_ok), "details": {"|A|": A_len, "|C|": C_len, "C/A": ratio_CA}})

    patt = "FLAT" if all(r["passed"] for r in rules) else None
    return {"pattern": patt, "rules": rules, "points": win, "debug": {"types": types, "prices": prices}}


def detect_triangle_rules(series: Series, *, lookback_pivot: int = 3) -> Dict[str, Any]:
    """
    Triangle rules:
      - ใช้ 5 จุดสลับชนิดสิ้นสุดที่ E: types ∈ {H,L,H,L,H} หรือ {L,H,L,H,L}
      - Contracting: ชุด highs ลดลงต่อเนื่อง และชุด lows สูงขึ้นต่อเนื่อง
        หรือ Expanding: ชุด highs สูงขึ้นต่อเนื่อง และชุด lows ลดลงต่อเนื่อง
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < 5:
        return {"pattern": None, "rules": [], "points": []}

    win = swings[-5:]
    types = [p["type"] for p in win]
    prices = [p["price"] for p in win]
    if types not in (["H","L","H","L","H"], ["L","H","L","H","L"]):
        return {"pattern": None, "rules": [], "points": []}

    highs = [p["price"] for p in win if p["type"] == "H"]
    lows  = [p["price"] for p in win if p["type"] == "L"]

    contracting = (all(x > y for x, y in zip(highs, highs[1:])) and
                   all(x < y for x, y in zip(lows,  lows[1:])))
    expanding   = (all(x < y for x, y in zip(highs, highs[1:])) and
                   all(x > y for x, y in zip(lows,  lows[1:])))

    rules = [
        {"name": "Alternating 5-leg structure (A-B-C-D-E)", "passed": True, "details": {"types": types}},
        {"name": "Contracting highs/lows OR Expanding highs/lows",
         "passed": bool(contracting or expanding),
         "details": {"mode": "Contracting" if contracting else ("Expanding" if expanding else "None")}},
    ]

    patt = "TRIANGLE" if all(r["passed"] for r in rules) else None
    return {"pattern": patt, "rules": rules, "points": win, "debug": {"types": types, "prices": prices}}

# =============================================================================
# Aggregator
# =============================================================================

def detect_patterns_rules(series: Series) -> Dict[str, Any]:
    """
    รวมผลตรวจแบบ Rules-Only ทั้งหมด
    """
    detectors = [
        detect_elliott_rules,
        detect_zigzag_rules,
        detect_flat_rules,
        detect_triangle_rules,
    ]
    results: List[Dict[str, Any]] = []
    for det in detectors:
        try:
            res = det(series)
        except Exception as e:
            res = {"pattern": None, "rules": [{"name": "error", "passed": False, "details": {"error": str(e)}}], "points": []}
        if res.get("pattern"):
            results.append(res)
    return {"patterns": results}
