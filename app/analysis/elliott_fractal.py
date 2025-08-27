# app/analysis/elliott_fractal.py
# -----------------------------------------------------------------------------
# Elliott Wave — FRACTAL VALIDATOR LAYER
# ตรวจ "subwave structure" ตาม Fractal Hierarchy จากสคีมา
# ทำงานต่อยอดจากผล RULES Layer (analyze_elliott_rules_v2)
# -----------------------------------------------------------------------------
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Literal, Any
import os
import json

import numpy as np
import pandas as pd

# ใช้ RULES Layer ที่เราสร้างไว้
from .elliott_rules import (
    analyze_elliott_rules_v2,
    load_schema as _load_schema_rules,
)

# -----------------------------------------------------------------------------
# พื้นฐานสวิง/พิเวต (คัดลอกแบบย่อเพื่อปรับพารามิเตอร์ซ้อนชั้นได้อิสระ)
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
Direction = Literal["up", "down", "side"]


def _dir(a: float, b: float) -> Direction:
    if b > a:
        return "up"
    if b < a:
        return "down"
    return "side"


def _slice_df(df: pd.DataFrame, i0: int, i1: int) -> pd.DataFrame:
    i0 = max(0, int(i0))
    i1 = min(len(df) - 1, int(i1))
    return df.iloc[i0 : i1 + 1]


# -----------------------------------------------------------------------------
# Fractal subwave validators (best-effort)
# -----------------------------------------------------------------------------
@dataclass
class SubCheck:
    label: str
    expected: str  # "5" หรือ "3"
    observed_legs: int
    pass_count: bool
    detail: Dict[str, Any]


def _count_alternations(sw: pd.DataFrame) -> int:
    """นับจำนวนจุดสวิง (legs) แบบ HLHL... (จำนวนจุด = ขา)."""
    if sw.empty:
        return 0
    types = sw["type"].tolist()
    # รวมต่อเนื่องซ้ำชนิดเดียวกันให้เหลือตัวแทนเดียว (กันสัญญาณรบกวน)
    compact: List[str] = []
    for t in types:
        if not compact or compact[-1] != t:
            compact.append(t)
    return len(compact)


def _want_odd_leg(target: str) -> int:
    # โครง 3 คลื่น = 4 จุดสวิง (H-L-H-L หรือกลับกัน) → legs (จุด) ควรเป็นเลขคู่ แต่จำนวน "ช่วง" = 3
    # เพื่อความง่าย เราเทียบจำนวนจุดสวิงกับเกณฑ์คร่าว ๆ
    return 5 if target == "5" else 3


def _pass_by_range(observed: int, target: str) -> Tuple[bool, str]:
    if target == "5":
        # ยอมรับ 5±2 จุดสวิง (เผื่อ noisy TF) แต่จะบันทึกรายละเอียดไว้
        return (observed >= 5 and observed <= 7), "expect≈5"
    else:
        # สำหรับ 3 คลื่น ยอมรับ 3–5 จุดสวิง
        return (observed >= 3 and observed <= 5), "expect≈3"


def _validate_subwaves_for_leg(
    df: pd.DataFrame,
    sub_pivot: Tuple[int, int],
    expected_seq: List[str],
) -> Tuple[List[SubCheck], bool]:
    """
    แบ่งช่วงย่อยเท่า ๆ กันตามจำนวน expected_seq แบบ best-effort
    แล้วตรวจจำนวนสวิงย่อยให้ประมาณ 3 หรือ 5 ตามที่คาด
    หมายเหตุ: วิธีนี้เป็น heuristic สำหรับ RULES Layer; ระบบจริงควรใช้ segment ตาม pivot หัว-ท้ายของขาจริง
    """
    left, right = sub_pivot
    sw = _build_swings(df, left=left, right=right)
    if len(sw) < 3:
        return [], False

    n = len(df)
    k = len(expected_seq)
    # แบ่งหน้าต่างเป็น k ส่วนเท่า ๆ กัน (คร่าว ๆ)
    bounds = [int(round(i * (n - 1) / k)) for i in range(k + 1)]

    results: List[SubCheck] = []
    all_ok = True
    for i, exp in enumerate(expected_seq):
        a, b = bounds[i], bounds[i + 1]
        seg = _slice_df(df, a, b)
        sw_sub = _build_swings(seg, left=left, right=right)
        legs = _count_alternations(sw_sub)
        ok, note = _pass_by_range(legs, exp)
        results.append(
            SubCheck(
                label=f"subwave[{i+1}]",
                expected=exp,
                observed_legs=legs,
                pass_count=ok,
                detail={"note": note, "len_seg": len(seg), "pivot_left": left, "pivot_right": right},
            )
        )
        all_ok = all_ok and ok

    return results, all_ok


# -----------------------------------------------------------------------------
# Main API
# -----------------------------------------------------------------------------

def load_schema(path: Optional[str] = None) -> Dict[str, Any]:
    # reuse ของ RULES layer (สคีมาเดียวกัน)
    return _load_schema_rules(path)


def analyze_elliott_fractal(
    df: pd.DataFrame,
    *,
    schema_path: Optional[str] = None,
    degree: str = "Minute",
    sub_pivot_left: int = 1,
    sub_pivot_right: int = 1,
) -> Dict[str, Any]:
    """
    ทำงาน 2 ขั้น:
    1) เรียก RULES Layer เพื่อระบุ pattern หลัก + ตัดหน้าต่างสวิงล่าสุด
    2) ตรวจ Fractal Subwaves ภายในหน้าต่างนั้นเทียบกับ schema.fractal_hierarchy.subwave_structures
    """
    schema = load_schema(schema_path)

    base = analyze_elliott_rules_v2(df, schema_path=schema_path)
    pattern: str = base.get("pattern", "UNKNOWN")
    debug = base.get("debug", {})

    # ถ้าไม่พบแพทเทิร์นหลัก ก็ส่งกลับผล RULES เดิมพร้อมธง
    if pattern == "UNKNOWN" or "window_indices" not in debug:
        base.setdefault("fractal", {})
        base["fractal"]["checked"] = False
        base["fractal"]["reason"] = "no_base_pattern"
        return base

    # ตัดหน้าต่างข้อมูลตามสวิงที่ RULES ใช้
    win_idxs: List[int] = debug["window_indices"]
    i0, i1 = min(win_idxs), max(win_idxs)
    df_win = _slice_df(df, i0, i1)

    # โครงที่คาดหวังตามสคีมา
    sub_structs = schema.get("fractal_hierarchy", {}).get("subwave_structures", {})
    expected_seq: List[str] = list(sub_structs.get(pattern, []))

    if not expected_seq:
        base.setdefault("fractal", {})
        base["fractal"]["checked"] = False
        base["fractal"]["reason"] = "no_expected_sub_structure"
        return base

    # ตรวจ subwaves โดยใช้ pivot ย่อย (ค่าเริ่มต้นละเอียดกว่า layer แรก)
    sub_checks, all_ok = _validate_subwaves_for_leg(
        df_win, (sub_pivot_left, sub_pivot_right), expected_seq
    )

    # แนบรายงานลงผลลัพธ์
    base.setdefault("fractal", {})
    base["fractal"]["checked"] = True
    base["fractal"]["degree"] = degree
    base["fractal"]["expected"] = expected_seq
    base["fractal"]["sub_checks"] = [
        {
            "label": c.label,
            "expected": c.expected,
            "observed_legs": c.observed_legs,
            "passed": c.pass_count,
            "detail": c.detail,
        }
        for c in sub_checks
    ]
    base["fractal"]["passed_all_subwaves"] = bool(all_ok)

    # convenience flags
    base["degree"] = degree
    base["completed"] = base.get("completed", False) and bool(all_ok)

    return base


# alias สำหรับเรียกง่ายใน services/wave_service.py
analyze_elliott_fractal_v1 = analyze_elliott_fractal
