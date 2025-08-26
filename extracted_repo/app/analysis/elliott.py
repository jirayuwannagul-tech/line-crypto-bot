# app/analysis/elliott.py
# -----------------------------------------------------------------------------
# Elliott Wave - RULES ONLY
# ตรวจสอบ "กฎ" ของรูปแบบหลักโดยไม่ใส่ heuristic/target/การคาดคะเนใด ๆ
# -----------------------------------------------------------------------------

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple
import numpy as np
import pandas as pd

Direction = Literal["up", "down", "side"]
Pattern = Literal["IMPULSE", "DIAGONAL", "ZIGZAG", "FLAT", "TRIANGLE", "UNKNOWN"]

__all__ = ["analyze_elliott_rules", "Pattern", "Direction"]

# =============================================================================
# Utilities: pivots & swings
# =============================================================================

def _fractals(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        win_h = high[i - left : i + right + 1]
        win_l = low[i - left : i + right + 1]
        if np.argmax(win_h) == left and high[i] == win_h.max():
            sh[i] = True
        if np.argmin(win_l) == left and low[i] == win_l.min():
            sl[i] = True
    return pd.Series(sh, index=df.index), pd.Series(sl, index=df.index)

def _build_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    is_sh, is_sl = _fractals(df, left=left, right=right)
    rows: List[Dict[str, object]] = []
    for i in range(len(df)):
        if is_sh.iat[i]:
            rows.append({"idx": i, "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i], "price": float(df["high"].iat[i]), "type": "H"})
        if is_sl.iat[i]:
            rows.append({"idx": i, "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i], "price": float(df["low"].iat[i]), "type": "L"})
    if not rows:
        return pd.DataFrame(columns=["idx", "timestamp", "price", "type"])
    sw = pd.DataFrame.from_records(rows).sort_values("idx").reset_index(drop=True)
    cleaned: List[Dict[str, object]] = []
    for r in sw.to_dict("records"):
        if not cleaned:
            cleaned.append(r)
            continue
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

def _leg_len(a: float, b: float) -> float:
    return abs(b - a)

def _retracement_ratio(a0: float, a1: float, b: float) -> Optional[float]:
    if a1 == a0: return None
    if a1 > a0: return (a1 - b) / (a1 - a0)
    else: return (b - a1) / (a0 - a1)

def _ratio(val: float, base: float) -> Optional[float]:
    if base == 0: return None
    return abs(val) / abs(base)

def _dir(a: float, b: float) -> Direction:
    if b > a: return "up"
    if b < a: return "down"
    return "side"

# =============================================================================
# Rule reporting
# =============================================================================
@dataclass
class Rule:
    name: str
    passed: bool
    details: Dict[str, object]

def _report(pattern: Pattern, rules: List[Rule], win: pd.DataFrame) -> Dict[str, object]:
    # ✅ wave_label = คำอธิบายคลื่นตามกฎ ไม่ใช่ logic
    wave_label = "UNKNOWN"
    if pattern == "IMPULSE":
        wave_label = "Wave 1-5"
    elif pattern == "DIAGONAL":
        wave_label = "Wave 1/5 (Diagonal)"
    elif pattern == "ZIGZAG":
        wave_label = "Wave A-B-C (Zigzag)"
    elif pattern == "FLAT":
        wave_label = "Wave A-B-C (Flat)"
    elif pattern == "TRIANGLE":
        wave_label = "Wave A-B-C-D-E"

    return {
        "pattern": pattern,
        "wave_label": wave_label,   # ✅ แค่บอกประเภท ไม่คาดการณ์
        "rules": [{"name": r.name, "passed": r.passed, "details": r.details} for r in rules],
        "debug": {
            "swings": win.tail(12).to_dict("records"),
            "window_indices": win["idx"].tolist(),
            "window_types": win["type"].tolist(),
            "window_prices": win["price"].tolist(),
        },
    }

# =============================================================================
# RULE CHECKERS
# =============================================================================
def _check_impulse_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    if len(sw) < 6:
        return None
    for end in range(len(sw), 5, -1):
        win = sw.iloc[end - 6 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
            continue
        direction = "up" if types[-1] == "H" else "down"
        p0, p1, p2, p3, p4, p5 = prices
        w1 = _leg_len(p0, p1)
        w3 = _leg_len(p2, p3)
        w5 = _leg_len(p4, p5)
        rules: List[Rule] = []
        r1_ok = (p2 > p0) if direction == "up" else (p2 < p0)
        rules.append(Rule("Wave2 does not retrace beyond start of Wave1", bool(r1_ok), {"p0": p0, "p2": p2, "direction": direction}))
        shortest = min(w1, w3, w5)
        r2_ok = (w3 > shortest) or (w3 == shortest and not (w3 == w1 == w5))
        rules.append(Rule("Wave3 is not the shortest among motive (1,3,5)", bool(r2_ok), {"w1": w1, "w3": w3, "w5": w5}))
        if direction == "up":
            r3_ok = (p4 > p1)
        else:
            r3_ok = (p4 < p1)
        rules.append(Rule("Wave4 does not overlap Wave1 price territory", bool(r3_ok), {"p1": p1, "p4": p4, "direction": direction}))
        all_pass = all(r.passed for r in rules)
        if all_pass:
            return _report("IMPULSE", rules, win)
        if (not r3_ok) and rules[0].passed and rules[1].passed:
            return _report("DIAGONAL", rules, win)
    return None

def _check_zigzag_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    if len(sw) < 4:
        return None
    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in (["H","L","H","L"], ["L","H","L","H"]):
            continue
        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)
        if dir_A == "side": continue
        rules: List[Rule] = []
        rB = _retracement_ratio(p0, p1, p2)
        r1_ok = rB is not None and (0.382 <= rB <= 0.618)
        rules.append(Rule("B retraces 38.2%–61.8% of A", bool(r1_ok), {"B_retrace": float(rB) if rB is not None else None}))
        r2_ok = (_dir(p2, p3) == dir_A)
        rules.append(Rule("C moves in the same direction as A", bool(r2_ok), {"dir_A": dir_A, "dir_C": _dir(p2, p3)}))
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        ratio_CA = _ratio(C_len, A_len) or 0.0
        r3_ok = (0.85 <= ratio_CA <= 1.15) or (1.618 * 0.85 <= ratio_CA <= 1.618 * 1.15)
        rules.append(Rule("|C| ≈ |A| or ≈ 1.618×|A| (±15%)", bool(r3_ok), {"|A|": A_len, "|C|": C_len, "C/A": ratio_CA}))
        if all(r.passed for r in rules):
            return _report("ZIGZAG", rules, win)
    return None

def _check_flat_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    if len(sw) < 4:
        return None
    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in (["H","L","H","L"], ["L","H","L","H"]):
            continue
        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)
        if dir_A == "side": continue
        rules: List[Rule] = []
        rB = _retracement_ratio(p0, p1, p2)
        r1_ok = rB is not None and (0.90 <= rB <= 1.10)
        rules.append(Rule("B retraces ~90%–110% of A", bool(r1_ok), {"B_retrace": float(rB) if rB is not None else None}))
        r2_ok = (_dir(p2, p3) == dir_A)
        rules.append(Rule("C moves in the same direction as A", bool(r2_ok), {"dir_A": dir_A, "dir_C": _dir(p2, p3)}))
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        ratio_CA = _ratio(C_len, A_len) or 0.0
        r3_ok = (0.85 <= ratio_CA <= 1.15) or (1.618 * 0.85 <= ratio_CA <= 1.618 * 1.15)
        rules.append(Rule("|C| ≈ |A| or ≈ 1.618×|A| (±15%)", bool(r3_ok), {"|A|": A_len, "|C|": C_len, "C/A": ratio_CA}))
        if all(r.passed for r in rules):
            return _report("FLAT", rules, win)
    return None

def _check_triangle_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    if len(sw) < 5:
        return None
    for end in range(len(sw), 4, -1):
        win = sw.iloc[end - 5 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in (["H","L","H","L","H"], ["L","H","L","H","L"]):
            continue
        highs = [p for t, p in zip(types, prices) if t == "H"]
        lows  = [p for t, p in zip(types, prices) if t == "L"]
        if len(highs) < 3 or len(lows) < 3:
            continue
        contracting = (all(x > y for x, y in zip(highs, highs[1:])) and all(x < y for x, y in zip(lows,  lows[1:])))
        expanding   = (all(x < y for x, y in zip(highs, highs[1:])) and all(x > y for x, y in zip(lows,  lows[1:])))
        rules = [
            Rule("Alternating 5-leg structure (A-B-C-D-E)", True, {"types": types}),
            Rule("Contracting highs/lows OR Expanding highs/lows", bool(contracting or expanding), {"mode": "Contracting" if contracting else ("Expanding" if expanding else "None")}),
        ]
        if all(r.passed for r in rules):
            return _report("TRIANGLE", rules, win)
    return None

# =============================================================================
# Public API
# =============================================================================
def analyze_elliott_rules(df: pd.DataFrame, *, pivot_left: int = 2, pivot_right: int = 2, max_swings: int = 30) -> Dict[str, object]:
    needed = {"high", "low", "close"}
    if not needed.issubset(df.columns):
        return {"pattern": "UNKNOWN", "wave_label": "UNKNOWN", "rules": [{"name": "missing_columns", "passed": False, "details": {"columns": list(df.columns)}}], "debug": {}}
    sw = _build_swings(df, left=pivot_left, right=pivot_right)
    if len(sw) == 0:
        return {"pattern": "UNKNOWN", "wave_label": "UNKNOWN", "rules": [{"name": "no_swings", "passed": False, "details": {}}], "debug": {}}
    if len(sw) > max_swings:
        sw = sw.tail(max_swings).reset_index(drop=True)
    res = _check_impulse_rules(sw) or _check_zigzag_rules(sw) or _check_flat_rules(sw) or _check_triangle_rules(sw)
    if res is not None:
        return res
    return {"pattern": "UNKNOWN", "wave_label": "UNKNOWN", "rules": [{"name": "no_pattern_rules_matched", "passed": False, "details": {}}], "debug": {"swings": sw.tail(12).to_dict("records")}}

# ✅ backward compatibility
def analyze_elliott(df: pd.DataFrame, **kwargs) -> Dict[str, object]:
    result = analyze_elliott_rules(df, **kwargs)
    if "completed" not in result:
        result["completed"] = False
    if "current" not in result:
        result["current"] = {}
    if "next" not in result:
        result["next"] = {}
    if "targets" not in result:
        result["targets"] = {}
    return result
