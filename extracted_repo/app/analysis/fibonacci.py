# app/analysis/fibonacci.py
# =============================================================================
# Fibonacci Tools
# -----------------------------------------------------------------------------
# - คำนวณ Fibonacci retracement / extension
# - ตรวจหา "Fibo Cluster" (ระดับหลายชุดที่ใกล้กัน)
# - ใช้ได้ทั้งขาขึ้น/ขาลง; ไม่พึ่ง external libs
# =============================================================================
from __future__ import annotations

from typing import Dict, List, Literal, Tuple, Optional
from collections import OrderedDict

Number = float
Direction = Literal["up", "down"]

__all__ = [
    "fib_levels",
    "fib_extensions",
    "FIB_RETRACEMENTS",
    "FIB_EXTENSIONS",
    "detect_fib_cluster",
    "merge_levels",
]

# =============================================================================
# Constants
# =============================================================================
FIB_RETRACEMENTS: Tuple[float, ...] = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
FIB_EXTENSIONS: Tuple[float, ...]   = (1.272, 1.414, 1.618, 2.0, 2.618, 3.618)

# =============================================================================
# Helpers
# =============================================================================
def _detect_direction(A: Number, B: Number) -> Direction:
    if B > A:
        return "up"
    elif B < A:
        return "down"
    else:
        raise ValueError("A and B must not be equal.")

def _key(r: float) -> str:
    return f"{r:.3f}".rstrip("0").rstrip(".")

# =============================================================================
# Public API
# =============================================================================
def fib_levels(
    A: Number,
    B: Number,
    ratios: Tuple[float, ...] = FIB_RETRACEMENTS,
) -> Dict[str, object]:
    """
    Fibonacci retracement ระหว่าง A->B
    Returns dict {direction,A,B,levels}
    """
    A = float(A); B = float(B)
    direction = _detect_direction(A, B)
    diff = B - A

    levels: "OrderedDict[str,float]" = OrderedDict()
    for r in ratios:
        if direction == "up":
            price = B - (diff * r)
        else:
            price = B + ((A - B) * r)
        levels[_key(r)] = float(price)

    return {"direction": direction, "A": A, "B": B, "levels": levels}

def fib_extensions(
    A: Number,
    B: Number,
    ratios: Tuple[float, ...] = FIB_EXTENSIONS,
) -> Dict[str, object]:
    """
    Fibonacci extension ต่อจากช่วง A->B
    Returns dict {direction,A,B,levels}
    """
    A = float(A); B = float(B)
    direction = _detect_direction(A, B)
    length = abs(B - A)

    levels: "OrderedDict[str,float]" = OrderedDict()
    for r in ratios:
        if direction == "up":
            price = B + (length * (r - 1.0))
        else:
            price = B - (length * (r - 1.0))
        levels[_key(r)] = float(price)

    return {"direction": direction, "A": A, "B": B, "levels": levels}

# =============================================================================
# Cluster Utilities
# =============================================================================
def merge_levels(*level_dicts: Dict[str, float]) -> Dict[str, float]:
    """รวม fib levels หลายชุดเป็น dict เดียว"""
    merged: Dict[str, float] = {}
    for ld in level_dicts:
        if not ld:
            continue
        for k, v in ld.items():
            merged[k] = float(v)
    return merged

def detect_fib_cluster(
    levels: Dict[str, float],
    *,
    tolerance_pct: float = 0.003,   # 0.3%
    min_points: int = 2
) -> Optional[Dict[str, object]]:
    """
    ตรวจหา "คลัสเตอร์" ของระดับ fib ที่อยู่ใกล้กัน
    Returns dict {center,members,spread_pct} | None
    """
    if not levels:
        return None

    items = sorted(((k, float(v)) for k, v in levels.items()), key=lambda x: x[1])
    best: Optional[Dict[str, object]] = None
    n = len(items)

    for i in range(n):
        cluster: List[Tuple[str, float]] = [items[i]]
        for j in range(i+1, n):
            tmp = cluster + [items[j]]
            prices = [p for _, p in tmp]
            center = sum(prices) / len(prices)
            max_dev = max(abs(p - center) / center for p in prices)
            if max_dev <= tolerance_pct:
                cluster = tmp
            else:
                break

        if len(cluster) >= min_points:
            prices = [p for _, p in cluster]
            center = sum(prices) / len(prices)
            spread = (max(prices) - min(prices)) / center if center else 0.0
            cand = {"center": float(center), "members": cluster, "spread_pct": float(spread)}

            if best is None:
                best = cand
            else:
                if len(cluster) > len(best["members"]):
                    best = cand
                elif len(cluster) == len(best["members"]) and cand["spread_pct"] < best["spread_pct"]:
                    best = cand
    return best
