# app/analysis/elliott.py
# -----------------------------------------------------------------------------
# Elliott Wave - RULES ONLY
# ตรวจสอบ "กฎ" ของรูปแบบหลักโดยไม่ใส่ heuristic/target/การคาดคะเนใด ๆ
# คืนค่าผลลัพธ์แบบ:
# {
#   "pattern": "IMPULSE|DIAGONAL|ZIGZAG|FLAT|TRIANGLE|UNKNOWN",
#   "rules": [
#       {"name": "...", "passed": true/false, "details": {...}},
#       ...
#   ],
#   "debug": {
#       "swings": [...],          # รายการสวิงล่าสุด
#       "window_indices": [...],  # index ของสวิงที่ใช้ตัดสิน
#       "window_types": [...],    # H/L
#       "window_prices": [...]
#   }
# }
# หมายเหตุ:
# - ไม่มีการฟันธงว่า "completed/progress" และไม่มี Fibonacci targets
# - ไม่มี heuristic ใด ๆ (เช่น breakout factor, median, projection)
# - DIAGONAL: ระบุเมื่อโครงสร้างเหมือน impulse แต่ Wave4 ซ้อนทับ (overlap) Wave1
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
    """Boolean Series for swing high / swing low via simple fractal logic."""
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
    """Return ordered swings with columns: ['idx','timestamp','price','type'] where type in {'H','L'}."""
    is_sh, is_sl = _fractals(df, left=left, right=right)
    rows: List[Dict[str, object]] = []
    for i in range(len(df)):
        if is_sh.iat[i]:
            rows.append({
                "idx": i,
                "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i],
                "price": float(df["high"].iat[i]),
                "type": "H",
            })
        if is_sl.iat[i]:
            rows.append({
                "idx": i,
                "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i],
                "price": float(df["low"].iat[i]),
                "type": "L",
            })

    if not rows:
        return pd.DataFrame(columns=["idx", "timestamp", "price", "type"])

    sw = pd.DataFrame.from_records(rows)
    if "idx" not in sw.columns:
        return pd.DataFrame(columns=["idx", "timestamp", "price", "type"])

    sw = sw.sort_values("idx").reset_index(drop=True)

    # enforce alternation by removing duplicates in succession (keep more extreme)
    cleaned: List[Dict[str, object]] = []
    for r in sw.to_dict("records"):
        if not cleaned:
            cleaned.append(r)
            continue
        if cleaned[-1]["type"] == r["type"]:
            if r["type"] == "H":
                if r["price"] >= cleaned[-1]["price"]:
                    cleaned[-1] = r
            else:  # "L"
                if r["price"] <= cleaned[-1]["price"]:
                    cleaned[-1] = r
        else:
            cleaned.append(r)
    return pd.DataFrame(cleaned)


def _leg_len(a: float, b: float) -> float:
    return abs(b - a)


def _retracement_ratio(a0: float, a1: float, b: float) -> Optional[float]:
    """
    Retracement of leg A (a0->a1) by point b (end of B).
    For up A: ratio = (a1 - b) / (a1 - a0)
    For down A: ratio = (b - a1) / (a0 - a1)
    """
    if a1 == a0:
        return None
    if a1 > a0:  # up
        return (a1 - b) / (a1 - a0)
    else:  # down
        return (b - a1) / (a0 - a1)


def _ratio(val: float, base: float) -> Optional[float]:
    if base == 0:
        return None
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
    return {
        "pattern": pattern,
        "rules": [{"name": r.name, "passed": r.passed, "details": r.details} for r in rules],
        "debug": {
            "swings": win.tail(12).to_dict("records"),
            "window_indices": win["idx"].tolist(),
            "window_types": win["type"].tolist(),
            "window_prices": win["price"].tolist(),
        },
    }

# =============================================================================
# RULE CHECKERS (no heuristics/targets/completion)
# =============================================================================

def _check_impulse_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Impulse rules only:
       - Alternation ends with motive extreme (L-H-L-H-L-H or H-L-H-L-H-L)
       - Wave2 does not retrace beyond start of Wave1
       - Wave3 not the shortest among motive waves (1,3,5)
       - Wave4 does not overlap Wave1 price territory
    """
    if len(sw) < 6:
        return None

    for end in range(len(sw), 5, -1):
        win = sw.iloc[end - 6 : end]  # 6 points -> 5 legs
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

        # Rule 1: Wave2 not beyond Wave1 start
        r1_ok = (p2 > p0) if direction == "up" else (p2 < p0)
        rules.append(Rule(
            name="Wave2 does not retrace beyond start of Wave1",
            passed=bool(r1_ok),
            details={"p0": p0, "p2": p2, "direction": direction},
        ))

        # Rule 2: Wave3 not the shortest (among 1,3,5)
        shortest = min(w1, w3, w5)
        r2_ok = (w3 > shortest) or (w3 == shortest and not (w3 == w1 == w5))
        rules.append(Rule(
            name="Wave3 is not the shortest among motive (1,3,5)",
            passed=bool(r2_ok),
            details={"w1": w1, "w3": w3, "w5": w5},
        ))

        # Rule 3: Wave4 no overlap with Wave1 price territory
        if direction == "up":
            r3_ok = (p4 > p1)
        else:
            r3_ok = (p4 < p1)
        rules.append(Rule(
            name="Wave4 does not overlap Wave1 price territory",
            passed=bool(r3_ok),
            details={"p1": p1, "p4": p4, "direction": direction},
        ))

        # สรุป: ถ้าทุกข้อผ่าน ⇒ IMPULSE; ถ้า fail เฉพาะ r3 (overlap) แต่ข้ออื่นผ่าน ⇒ DIAGONAL
        all_pass = all(r.passed for r in rules)
        if all_pass:
            return _report("IMPULSE", rules, win)

        # DIAGONAL condition: overlap only
        if (not r3_ok) and rules[0].passed and rules[1].passed:
            return _report("DIAGONAL", rules, win)

    return None


def _check_zigzag_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Zigzag rules (ใช้ tolerance แบบตำรา):
       - โครงสร้าง 4 จุดสลับ H/L: H-L-H-L หรือ L-H-L-H
       - B retrace ของ A อยู่ในช่วง ~38.2% ถึง ~61.8%
       - C เดินทางทิศเดียวกับ A
       - ความยาว C ~ เท่า A (±15%) หรือ ~1.618×A (±15%)
    """
    if len(sw) < 4:
        return None

    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]  # P0 P1 P2 P3
        types = win["type"].tolist()
        prices = win["price"].tolist()

        if types not in (["H","L","H","L"], ["L","H","L","H"]):
            continue

        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)
        if dir_A == "side":
            continue

        rules: List[Rule] = []

        # Rule 1: B retracement of A in [0.382, 0.618]
        rB = _retracement_ratio(p0, p1, p2)
        r1_ok = rB is not None and (0.382 <= rB <= 0.618)
        rules.append(Rule(
            name="B retraces 38.2%–61.8% of A",
            passed=bool(r1_ok),
            details={"B_retrace": float(rB) if rB is not None else None},
        ))

        # Rule 2: C same direction as A
        r2_ok = (_dir(p2, p3) == dir_A)
        rules.append(Rule(
            name="C moves in the same direction as A",
            passed=bool(r2_ok),
            details={"dir_A": dir_A, "dir_C": _dir(p2, p3)},
        ))

        # Rule 3: |C| ≈ |A| (±15%) หรือ ≈ 1.618×|A| (±15%)
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        ratio_CA = _ratio(C_len, A_len) or 0.0
        r3_ok = (0.85 <= ratio_CA <= 1.15) or (1.618 * 0.85 <= ratio_CA <= 1.618 * 1.15)
        rules.append(Rule(
            name="|C| ≈ |A| or ≈ 1.618×|A| (±15%)",
            passed=bool(r3_ok),
            details={"|A|": A_len, "|C|": C_len, "C/A": ratio_CA},
        ))

        if all(r.passed for r in rules):
            return _report("ZIGZAG", rules, win)

    return None


def _check_flat_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Flat rules:
       - โครงสร้าง 4 จุดสลับ H/L
       - B retrace ลึกของ A ~90%–110% (รวมกรณี B เกินเล็กน้อย)
       - C ทิศเดียวกับ A
       - |C| ≈ |A| (±15%) หรือ ≈ 1.618×|A| (±15%) (Expanded Flat)
    """
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
        if dir_A == "side":
            continue

        rules: List[Rule] = []

        # Rule 1: B retrace ~90%–110% ของ A
        rB = _retracement_ratio(p0, p1, p2)
        r1_ok = rB is not None and (0.90 <= rB <= 1.10)
        rules.append(Rule(
            name="B retraces ~90%–110% of A",
            passed=bool(r1_ok),
            details={"B_retrace": float(rB) if rB is not None else None},
        ))

        # Rule 2: C ทิศเดียวกับ A
        r2_ok = (_dir(p2, p3) == dir_A)
        rules.append(Rule(
            name="C moves in the same direction as A",
            passed=bool(r2_ok),
            details={"dir_A": dir_A, "dir_C": _dir(p2, p3)},
        ))

        # Rule 3: |C| ≈ |A| (±15%) หรือ ≈ 1.618×|A| (±15%)
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        ratio_CA = _ratio(C_len, A_len) or 0.0
        r3_ok = (0.85 <= ratio_CA <= 1.15) or (1.618 * 0.85 <= ratio_CA <= 1.618 * 1.15)
        rules.append(Rule(
            name="|C| ≈ |A| or ≈ 1.618×|A| (±15%)",
            passed=bool(r3_ok),
            details={"|A|": A_len, "|C|": C_len, "C/A": ratio_CA},
        ))

        if all(r.passed for r in rules):
            return _report("FLAT", rules, win)

    return None


def _check_triangle_rules(sw: pd.DataFrame) -> Optional[Dict[str, object]]:
    """Triangle rules:
       - มี 5 สวิงสลับสิ้นสุดที่ E: (H,L,H,L,H) หรือ (L,H,L,H,L)
       - Contracting: ชุด high ลดลงต่อเนื่อง และชุด low สูงขึ้นต่อเนื่อง
         หรือ Expanding: ชุด high สูงขึ้นต่อเนื่อง และชุด low ลดลงต่อเนื่อง
    """
    if len(sw) < 5:
        return None

    for end in range(len(sw), 4, -1):
        win = sw.iloc[end - 5 : end]  # A B C D E
        types = win["type"].tolist()
        prices = win["price"].tolist()

        if types not in (["H","L","H","L","H"], ["L","H","L","H","L"]):
            continue

        highs = [p for t, p in zip(types, prices) if t == "H"]
        lows  = [p for t, p in zip(types, prices) if t == "L"]

        if len(highs) < 3 or len(lows) < 3:
            continue

        contracting = (all(x > y for x, y in zip(highs, highs[1:])) and
                       all(x < y for x, y in zip(lows,  lows[1:])))
        expanding   = (all(x < y for x, y in zip(highs, highs[1:])) and
                       all(x > y for x, y in zip(lows,  lows[1:])))

        rules = [
            Rule(
                name="Alternating 5-leg structure (A-B-C-D-E)",
                passed=True,
                details={"types": types},
            ),
            Rule(
                name="Contracting highs/lows OR Expanding highs/lows",
                passed=bool(contracting or expanding),
                details={"mode": "Contracting" if contracting else ("Expanding" if expanding else "None")},
            ),
        ]

        if all(r.passed for r in rules):
            return _report("TRIANGLE", rules, win)

    return None

# =============================================================================
# Public API (RULES ONLY)
# =============================================================================

def analyze_elliott_rules(
    df: pd.DataFrame,
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
    max_swings: int = 30,
) -> Dict[str, object]:
    """
    ตรวจสอบเฉพาะ "กฎ" ของรูปแบบ Elliott Wave จาก OHLC DataFrame
    ต้องมีคอลัมน์อย่างน้อย: ['high','low','close']
    """
    needed = {"high", "low", "close"}
    if not needed.issubset(df.columns):
        return {
            "pattern": "UNKNOWN",
            "rules": [{"name": "missing_columns", "passed": False, "details": {"columns": list(df.columns)}}],
            "debug": {},
        }

    sw = _build_swings(df, left=pivot_left, right=pivot_right)
    if len(sw) == 0:
        return {"pattern": "UNKNOWN", "rules": [{"name": "no_swings", "passed": False, "details": {}}], "debug": {}}

    if len(sw) > max_swings:
        sw = sw.tail(max_swings).reset_index(drop=True)

    # Priority: Impulse/Diagonal -> Zigzag -> Flat -> Triangle
    res = _check_impulse_rules(sw)
    if res is not None:
        return res

    res = _check_zigzag_rules(sw)
    if res is not None:
        return res

    res = _check_flat_rules(sw)
    if res is not None:
        return res

    res = _check_triangle_rules(sw)
    if res is not None:
        return res

    # ไม่เข้ากฎใด ๆ
    return {
        "pattern": "UNKNOWN",
        "rules": [{"name": "no_pattern_rules_matched", "passed": False, "details": {}}],
        "debug": {"swings": sw.tail(12).to_dict("records")},
    }
# ✅ เพิ่มฟังก์ชันนี้ท้ายไฟล์ app/analysis/elliott.py
def analyze_elliott(df, **kwargs):
    """
    Backward compatibility wrapper for old imports.
    Calls analyze_elliott_rules with default or passed arguments.
    """
    return analyze_elliott_rules(df, **kwargs)
