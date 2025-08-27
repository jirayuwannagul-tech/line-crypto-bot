# app/analysis/elliott_rules.py
# -----------------------------------------------------------------------------
# Elliott Wave - RULES VALIDATOR (data-driven)
# อ่านสคีมา JSON แล้วตรวจแพทเทิร์นหลักตามกฎ (ไม่ใส่ heuristic/target)
# -----------------------------------------------------------------------------

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Literal, Any
import json
import os
import math

import numpy as np
import pandas as pd

# พยายามใช้ตัวสร้างสวิงจากไฟล์เดิม; ถ้า import ไม่ได้ ค่อยใช้ fallback ในไฟล์นี้
try:
    from .elliott import _build_swings  # type: ignore
except Exception:
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
        rows: List[Dict[str, Any]] = []
        for i in range(len(df)):
            if is_sh.iat[i]:
                rows.append({"idx": i, "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i], "price": float(df["high"].iat[i]), "type": "H"})
            if is_sl.iat[i]:
                rows.append({"idx": i, "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i], "price": float(df["low"].iat[i]), "type": "L"})
        if not rows:
            return pd.DataFrame(columns=["idx", "timestamp", "price", "type"])
        sw = pd.DataFrame.from_records(rows).sort_values("idx").reset_index(drop=True)
        cleaned: List[Dict[str, Any]] = []
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

Direction = Literal["up","down","side"]
Pattern = Literal["IMPULSE","DIAGONAL","ZIGZAG","FLAT","TRIANGLE","COMBINATION","UNKNOWN"]

# =============================================================================
# Utilities
# =============================================================================

def _leg_len(a: float, b: float) -> float:
    return abs(b - a)

def _dir(a: float, b: float) -> Direction:
    if b > a: return "up"
    if b < a: return "down"
    return "side"

def _ratio(val: float, base: float) -> Optional[float]:
    if base == 0: return None
    return abs(val) / abs(base)

def _retracement_ratio(a0: float, a1: float, b: float) -> Optional[float]:
    # รีเทรซจาก a1 กลับไปหา a0 แล้ว b อยู่ตรงไหน (0..1)
    if a1 == a0: return None
    if a1 > a0:  # ขึ้น
        return (a1 - b) / (a1 - a0)
    else:       # ลง
        return (b - a1) / (a0 - a1)

def _within(x: float, rng: Tuple[float, float], tol: float = 0.0) -> bool:
    return (rng[0] - tol) <= x <= (rng[1] + tol)

# =============================================================================
# Schema loader
# =============================================================================

def _default_schema_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "schemas", "elliott_rules.schema.json"))

def load_schema(path: Optional[str] = None) -> Dict[str, Any]:
    schema_path = path or _default_schema_path()
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)

# =============================================================================
# Report helpers
# =============================================================================

@dataclass
class RuleResult:
    name: str
    passed: bool
    details: Dict[str, Any]

def _base_report(pattern: Pattern, schema: Dict[str, Any], rules: List[RuleResult], win: pd.DataFrame, variant: Optional[str] = None) -> Dict[str, Any]:
    wave_labels = schema.get("output", {}).get("wave_labels", {})
    diagnostics = schema.get("diagnostics", {})
    debug_tail = int(diagnostics.get("debug_swings_tail", 12))

    return {
        "pattern": pattern,
        "variant": variant or "",
        "wave_label": wave_labels.get(pattern, "UNKNOWN"),
        "rules": [{"name": r.name, "passed": r.passed, "details": r.details} for r in rules],
        "debug": {
            "swings": win.tail(debug_tail).to_dict("records"),
            "window_indices": win["idx"].tolist(),
            "window_types": win["type"].tolist(),
            "window_prices": win["price"].tolist(),
        },
        "completed": False,
        "current": {},
        "next": {},
        "targets": {}
    }

# =============================================================================
# Pattern checkers (data-driven using schema)
# =============================================================================

def _check_impulse(schema: Dict[str, Any], sw: pd.DataFrame) -> Optional[Dict[str, Any]]:
    tol = schema["tolerances"]
    seqs = schema["detection"]["alt_hl_sequences"]
    min_legs = int(tol.get("min_impulse_legs", 6))

    if len(sw) < min_legs:
        return None

    for end in range(len(sw), min_legs - 1, -1):
        win = sw.iloc[end - min_legs : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in seqs:
            continue

        # กำหนดทิศจากจุดสุดท้าย
        direction = "up" if types[-1] == "H" else "down"
        p0, p1, p2, p3, p4, p5 = prices[:6]
        w1 = _leg_len(p0, p1)
        w3 = _leg_len(p2, p3)
        w5 = _leg_len(p4, p5)

        rules: List[RuleResult] = []

        # Rule: wave2 ไม่ล้ำจุดเริ่ม wave1
        r1_ok = (p2 > p0) if direction == "up" else (p2 < p0)
        rules.append(RuleResult("no_wave2_beyond_wave1_start", bool(r1_ok), {"p0": p0, "p2": p2, "direction": direction}))

        # Rule: wave3 ไม่สั้นสุดใน (1,3,5)
        shortest = min(w1, w3, w5)
        r2_ok = (w3 > shortest) or (w3 == shortest and not (w3 == w1 == w5))
        rules.append(RuleResult("wave3_not_shortest_vs_1_3_5", bool(r2_ok), {"w1": w1, "w3": w3, "w5": w5}))

        # Rule: wave4 ไม่ overlap wave1 territory (approx: จุดปลาย 4 ไม่ย้อนผ่านปลาย 1)
        if direction == "up":
            r3_ok = (p4 > p1)
        else:
            r3_ok = (p4 < p1)
        rules.append(RuleResult("no_wave1_4_overlap", bool(r3_ok), {"p1": p1, "p4": p4, "direction": direction}))

        if all(r.passed for r in rules):
            return _base_report("IMPULSE", schema, rules, win)

        # ถ้า fail ข้อ overlap แต่ข้ออื่นผ่าน → อาจเป็น Diagonal
        if (not r3_ok) and rules[0].passed and rules[1].passed:
            return _base_report("DIAGONAL", schema, rules, win, variant="LEADING_OR_ENDING")

    return None

def _check_zigzag(schema: Dict[str, Any], sw: pd.DataFrame) -> Optional[Dict[str, Any]]:
    seqs = schema["detection"]["abc_sequences"]
    tol_pct = float(schema["tolerances"]["ratio_tolerance_pct"])
    if len(sw) < 4: return None

    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in seqs:
            continue

        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)
        if dir_A == "side":
            continue

        rules: List[RuleResult] = []

        # B retrace shallow (≈ 0.382–0.618 ของ A)
        rB = _retracement_ratio(p0, p1, p2)
        rng = tuple(schema["fibonacci"]["default_windows"]["zigzag_B_of_A"])
        r1_ok = (rB is not None) and _within(float(rB), rng, tol=tol_pct)
        rules.append(RuleResult("B_is_3_retrace_shallow", bool(r1_ok), {"B_retrace": None if rB is None else float(rB), "range": rng}))

        # C same dir as A และนับเป็น motive (ตรงนี้ใช้ same dir เป็นหลัก; โครงย่อย 5 ให้ layer อื่นเช็ค)
        r2_ok = (_dir(p2, p3) == dir_A)
        rules.append(RuleResult("C_is_motive_5_same_dir_as_A", bool(r2_ok), {"dir_A": dir_A, "dir_C": _dir(p2, p3)}))

        # |C| ≈ |A| หรือ ≈ 1.618×|A|
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        CA = _ratio(C_len, A_len) or 0.0
        around1 = _within(CA, (0.85, 1.15))
        around1618 = _within(CA, (1.618*(1-0.15), 1.618*(1+0.15)))
        r3_ok = bool(around1 or around1618)
        rules.append(RuleResult("C_len_vs_A_targets", r3_ok, {"|A|": A_len, "|C|": C_len, "C/A": CA}))

        if all(r.passed for r in rules):
            return _base_report("ZIGZAG", schema, rules, win)

    return None

def _check_flat(schema: Dict[str, Any], sw: pd.DataFrame) -> Optional[Dict[str, Any]]:
    seqs = schema["detection"]["abc_sequences"]
    tol_pct = float(schema["tolerances"]["ratio_tolerance_pct"])
    if len(sw) < 4: return None

    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in seqs:
            continue

        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)
        if dir_A == "side":
            continue

        rules: List[RuleResult] = []

        # B retrace deep ≈ 0.90–1.10 ของ A (regular/running/expanded)
        rB = _retracement_ratio(p0, p1, p2)
        rng = tuple(schema["fibonacci"]["default_windows"]["flat_B_of_A"])
        r1_ok = (rB is not None) and _within(float(rB), rng, tol=tol_pct)
        rules.append(RuleResult("B_is_3_deep", bool(r1_ok), {"B_retrace": None if rB is None else float(rB), "range": rng}))

        # C ไปทางเดียวกับ A
        r2_ok = (_dir(p2, p3) == dir_A)
        rules.append(RuleResult("C_is_motive_5_same_dir_as_A", bool(r2_ok), {"dir_A": dir_A, "dir_C": _dir(p2, p3)}))

        # |C| ≈ |A| (±15%) หรือถ้า expanded จะยาว 1.272–1.618×A (ให้ผ่าน Guideline เบื้องต้น)
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        CA = _ratio(C_len, A_len) or 0.0
        ok_regular = _within(CA, (0.85, 1.15))
        ok_expanded = _within(CA, tuple(schema["fibonacci"]["default_windows"]["C_vs_A_expanded"]), tol=0.0)
        r3_ok = bool(ok_regular or ok_expanded)
        rules.append(RuleResult("C_vs_A_regular_or_expanded", r3_ok, {"|A|": A_len, "|C|": C_len, "C/A": CA}))

        if all(r.passed for r in rules):
            # ระบุ variant แบบคร่าว ๆ
            variant = ""
            if rB is not None and rB > 1.0 + tol_pct:
                if CA < 1.0:  # C สั้น → Running Flat
                    variant = "RUNNING"
                elif ok_expanded:
                    variant = "EXPANDED"
                else:
                    variant = "EXPANDED_OR_RUNNING"
            else:
                variant = "REGULAR"
            rep = _base_report("FLAT", schema, rules, win, variant=variant)
            return rep

    return None

def _check_triangle(schema: Dict[str, Any], sw: pd.DataFrame) -> Optional[Dict[str, Any]]:
    seqs = schema["detection"]["triangle_sequences"]
    if len(sw) < 5: return None

    for end in range(len(sw), 4, -1):
        win = sw.iloc[end - 5 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        if types not in seqs:
            continue

        highs = [p for t, p in zip(types, prices) if t == "H"]
        lows  = [p for t, p in zip(types, prices) if t == "L"]
        if len(highs) < 3 or len(lows) < 3:
            continue

        contracting = (all(x > y for x, y in zip(highs, highs[1:])) and all(x < y for x, y in zip(lows,  lows[1:])))
        expanding   = (all(x < y for x, y in zip(highs, highs[1:])) and all(x > y for x, y in zip(lows,  lows[1:])))

        rules = [
            RuleResult("five_legs_A_to_E", True, {"types": types}),
            RuleResult("each_leg_is_3", True, {"note": "ตรวจย่อยระดับ sub-pivots ในชั้นถัดไป"}),
            RuleResult("geometry_contracting_or_expanding", bool(contracting or expanding), {"mode": "CONTRACTING" if contracting else ("EXPANDING" if expanding else "NONE")}),
        ]

        if all(r.passed for r in rules):
            variant = "CONTRACTING" if contracting else ("EXPANDING" if expanding else "")
            return _base_report("TRIANGLE", schema, rules, win, variant=variant)

    return None

# =============================================================================
# Public API
# =============================================================================

def analyze_elliott_rules_v2(
    df: pd.DataFrame,
    *,
    schema_path: Optional[str] = None,
    pivot_left: Optional[int] = None,
    pivot_right: Optional[int] = None,
    max_swings: Optional[int] = None
) -> Dict[str, Any]:
    """
    Validator เวอร์ชัน data-driven:
    - อ่านกฎจากสคีมา
    - สร้างสวิง แล้วเช็ค IMPULSE/DIAGONAL/ZIGZAG/FLAT/TRIANGLE ตามลำดับ
    - ไม่ทำคาดการณ์/เป้า (targets) นอกเหนือ RULES
    """
    schema = load_schema(schema_path)

    needed = {"high", "low", "close"}
    if not needed.issubset(df.columns):
        return {"pattern": "UNKNOWN", "wave_label": "UNKNOWN", "rules": [{"name": "missing_columns", "passed": False, "details": {"columns": list(df.columns)}}], "debug": {}, "completed": False, "current": {}, "next": {}, "targets": {}}

    piv = schema["detection"]["pivots"]
    left = pivot_left if pivot_left is not None else int(piv.get("left", 2))
    right = pivot_right if pivot_right is not None else int(piv.get("right", 2))
    sw = _build_swings(df, left=left, right=right)

    if len(sw) == 0:
        return {"pattern": "UNKNOWN", "wave_label": "UNKNOWN", "rules": [{"name": "no_swings", "passed": False, "details": {}}], "debug": {}, "completed": False, "current": {}, "next": {}, "targets": {}}

    mx = schema["detection"].get("max_swings", 30)
    mx = max_swings if max_swings is not None else mx
    if len(sw) > int(mx):
        sw = sw.tail(int(mx)).reset_index(drop=True)

    # ลำดับตรวจ (เร็ว → ช้า); DIAGONAL ถูก infer จาก overlap case ใน impulse checker อยู่แล้ว
    res = (
        _check_impulse(schema, sw)
        or _check_zigzag(schema, sw)
        or _check_flat(schema, sw)
        or _check_triangle(schema, sw)
    )

    if res is not None:
        return res

    return {
        "pattern": "UNKNOWN",
        "wave_label": "UNKNOWN",
        "rules": [{"name": "no_pattern_rules_matched", "passed": False, "details": {}}],
        "debug": {"swings": sw.tail(12).to_dict("records")},
        "completed": False,
        "current": {},
        "next": {},
        "targets": {}
    }

# alias เพื่อใช้เหมือนฟังก์ชันเดิม
def analyze_elliott(df: pd.DataFrame, **kwargs) -> Dict[str, Any]:
    return analyze_elliott_rules_v2(df, **kwargs)
