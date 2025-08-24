# app/analysis/patterns.py
# =============================================================================
# Chart Patterns — RULES ONLY
# -----------------------------------------------------------------------------
# ตรวจจับรูปแบบจาก "กฎล้วน ๆ" (ไม่มี heuristic/target/การเดา label)
# Supported:
#   - Elliott (IMPULSE, DIAGONAL)
#   - Zigzag
#   - Flat
#   - Triangle
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
# Low-level helpers
# =============================================================================

def _swing_points(candles: List[Dict[str, Any]], left: int = 3, right: int = 3) -> List[Dict[str, Any]]:
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
            if r["type"] == "H":
                if r["price"] >= cleaned[-1]["price"]:
                    cleaned[-1] = r
            else:
                if r["price"] <= cleaned[-1]["price"]:
                    cleaned[-1] = r
        else:
            cleaned.append(r)
    return cleaned

def _leg_len(a: float, b: float) -> float: return abs(b - a)
def _dir(a: float, b: float) -> str:
    if b > a: return "up"
    if b < a: return "down"
    return "side"
def _retracement_ratio(a0: float, a1: float, b: float) -> Optional[float]:
    if a1 == a0: return None
    if a1 > a0: return (a1 - b) / (a1 - a0)
    else: return (b - a1) / (a0 - a1)
def _ratio(val: float, base: float) -> Optional[float]:
    if base == 0: return None
    return abs(val) / abs(base)

# =============================================================================
# RULE DETECTORS
# =============================================================================

def detect_elliott_rules(series: Series, *, window_points: int = 6, lookback_pivot: int = 3) -> Dict[str, Any]:
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
    w1, w3, w5 = _leg_len(p0, p1), _leg_len(p2, p3), _leg_len(p4, p5)
    rules = []
    r1_ok = (p2 > p0) if direction == "up" else (p2 < p0)
    rules.append({"name": "W2 not beyond W1 start", "passed": bool(r1_ok)})
    shortest = min(w1, w3, w5)
    r2_ok = (w3 > shortest) or (w3 == shortest and not (w3 == w1 == w5))
    rules.append({"name": "W3 not shortest", "passed": bool(r2_ok)})
    if direction == "up": r3_ok = (p4 > p1)
    else: r3_ok = (p4 < p1)
    rules.append({"name": "W4 no overlap W1", "passed": bool(r3_ok)})
    patt = "IMPULSE" if all(r["passed"] for r in rules) else ("DIAGONAL" if (not r3_ok) and r1_ok and r2_ok else None)
    return {"pattern": patt, "rules": rules, "points": win}

def detect_zigzag_rules(series: Series, *, lookback_pivot: int = 3) -> Dict[str, Any]:
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < 4:
        return {"pattern": None, "rules": [], "points": []}
    win = swings[-4:]
    types = [p["type"] for p in win]; prices = [p["price"] for p in win]
    if types not in (["H","L","H","L"], ["L","H","L","H"]): return {"pattern": None, "rules": [], "points": []}
    p0, p1, p2, p3 = prices; dir_A = _dir(p0, p1)
    rB = _retracement_ratio(p0, p1, p2)
    r1_ok = (rB is not None) and (0.382 <= rB <= 0.618)
    r2_ok = (_dir(p2, p3) == dir_A)
    A_len, C_len = _leg_len(p0, p1), _leg_len(p2, p3)
    ratio_CA = _ratio(C_len, A_len) or 0.0
    r3_ok = (0.85 <= ratio_CA <= 1.15) or ((1.618 * 0.85) <= ratio_CA <= (1.618 * 1.15))
    patt = "ZIGZAG" if (r1_ok and r2_ok and r3_ok) else None
    return {"pattern": patt, "rules": [{"name": "B retrace 38-61%", "passed": r1_ok},
            {"name": "C same dir A", "passed": r2_ok},
            {"name": "|C|≈|A| or 1.618x", "passed": r3_ok}], "points": win}

def detect_flat_rules(series: Series, *, lookback_pivot: int = 3) -> Dict[str, Any]:
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < 4: return {"pattern": None, "rules": [], "points": []}
    win = swings[-4:]; types = [p["type"] for p in win]; prices = [p["price"] for p in win]
    if types not in (["H","L","H","L"], ["L","H","L","H"]): return {"pattern": None, "rules": [], "points": []}
    p0, p1, p2, p3 = prices; dir_A = _dir(p0, p1)
    rB = _retracement_ratio(p0, p1, p2)
    r1_ok = (rB is not None) and (0.90 <= rB <= 1.10)
    r2_ok = (_dir(p2, p3) == dir_A)
    A_len, C_len = _leg_len(p0, p1), _leg_len(p2, p3)
    ratio_CA = _ratio(C_len, A_len) or 0.0
    r3_ok = (0.85 <= ratio_CA <= 1.15) or ((1.618 * 0.85) <= ratio_CA <= (1.618 * 1.15))
    patt = "FLAT" if (r1_ok and r2_ok and r3_ok) else None
    return {"pattern": patt, "rules": [{"name": "B retrace ~90-110%", "passed": r1_ok},
            {"name": "C same dir A", "passed": r2_ok},
            {"name": "|C|≈|A| or 1.618x", "passed": r3_ok}], "points": win}

def detect_triangle_rules(series: Series, *, lookback_pivot: int = 3) -> Dict[str, Any]:
    candles = series.get("candles", [])
    swings = _swing_points(candles, left=lookback_pivot, right=lookback_pivot)
    if len(swings) < 5: return {"pattern": None, "rules": [], "points": []}
    win = swings[-5:]; types = [p["type"] for p in win]; prices = [p["price"] for p in win]
    if types not in (["H","L","H","L","H"], ["L","H","L","H","L"]): return {"pattern": None, "rules": [], "points": []}
    highs = [p["price"] for p in win if p["type"] == "H"]; lows  = [p["price"] for p in win if p["type"] == "L"]
    contracting = (all(x > y for x, y in zip(highs, highs[1:])) and all(x < y for x, y in zip(lows, lows[1:])))
    expanding   = (all(x < y for x, y in zip(highs, highs[1:])) and all(x > y for x, y in zip(lows, lows[1:])))
    patt = "TRIANGLE" if (contracting or expanding) else None
    return {"pattern": patt, "rules": [{"name": "Alternating 5-leg", "passed": True},
            {"name": "Contracting/Expanding", "passed": bool(contracting or expanding)}], "points": win}

# =============================================================================
# Aggregator
# =============================================================================

def detect_patterns_rules(series: Series) -> Dict[str, Any]:
    detectors = [detect_elliott_rules, detect_zigzag_rules, detect_flat_rules, detect_triangle_rules]
    results: List[Dict[str, Any]] = []
    for det in detectors:
        try: res = det(series)
        except Exception as e: res = {"pattern": None, "rules": [{"name": "error", "passed": False, "details": {"error": str(e)}}], "points": []}
        if res.get("pattern"): results.append(res)
    return {"patterns": results}

# =============================================================================
# ✅ Stub Functions for tests
# =============================================================================

def detect_breakout(series: Series, lookback: int = 20) -> Dict[str, Any]:
    """Stub สำหรับ breakout"""
    return {
        "is_valid": False,
        "meta": {"direction": None, "lookback": lookback}
    }

def detect_inside_bar(series: Series) -> Dict[str, Any]:
    """Stub สำหรับ inside-bar"""
    return {
        "is_valid": False,
        "meta": {}
    }
