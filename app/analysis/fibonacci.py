# =============================================================================
# Fibonacci Tools
# -----------------------------------------------------------------------------
# - คำนวณ Fibonacci retracement / extension
# - ตรวจหา "Fibo Cluster" (ระดับหลายชุดที่ใกล้กัน)
# - ใช้ได้ทั้งขาขึ้น/ขาลง; ไม่พึ่ง external libs
# =============================================================================
from __future__ import annotations

from typing import Dict, List, Literal, Tuple, Optional, Any
from collections import OrderedDict
import math

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
FIB_EXTENSIONS:  Tuple[float, ...] = (1.272, 1.414, 1.618, 2.0, 2.618, 3.618)

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

def _is_number(x: Any) -> bool:
    try:
        fx = float(x)
        return math.isfinite(fx)
    except (TypeError, ValueError):
        return False

def _extract_levels(obj: Any) -> Dict[str, float]:
    """
    รองรับ 2 รูปแบบอินพุต:
    1) dict ของระดับโดยตรง: {"0.382": 12345.6, "0.5": 12222.2, ...}
    2) payload จาก fib_levels: {"direction": "...", "A":..., "B":..., "levels": {...}}

    คืน dict ที่เป็น {ชื่อสัดส่วน: ราคา(float)} โดยกรองเฉพาะตัวเลข
    """
    # รูปแบบ payload จาก fib_levels(...)
    if isinstance(obj, dict) and "levels" in obj and isinstance(obj["levels"], dict):
        src = obj["levels"]
    else:
        src = obj

    out: Dict[str, float] = {}
    if isinstance(src, dict):
        for k, v in src.items():
            if _is_number(v):
                out[str(k)] = float(v)
    return out

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
    Returns dict {"direction", "A", "B", "levels": OrderedDict[str,float]}
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
    Returns dict {"direction", "A", "B", "levels": OrderedDict[str,float]}
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
def merge_levels(*level_dicts: Dict[str, Any]) -> Dict[str, float]:
    """
    รวม fib levels หลายชุดเป็น dict เดียว
    - รับได้ทั้ง dict ตรง ๆ และ payload ที่มี key "levels"
    - กรองเฉพาะค่าที่เป็นตัวเลข
    """
    merged: Dict[str, float] = {}
    for ld in level_dicts:
        if not ld:
            continue
        extracted = _extract_levels(ld)
        for k, v in extracted.items():
            merged[k] = float(v)
    return merged

def detect_fib_cluster(
    levels_or_payload: Dict[str, Any],
    *,
    tolerance_pct: float = 0.003,   # window กว้างสุดราว 0.3% จาก center
    min_points: int = 2
) -> Optional[Dict[str, object]]:
    """
    ตรวจหา "คลัสเตอร์" ของระดับ fib ที่อยู่ใกล้กัน
    อินพุตยืดหยุ่น: รับ dict ระดับโดยตรง หรือ payload จาก fib_levels/fib_extensions

    Returns:
      dict {"center": float, "members": list[(name, value)], "spread_pct": float} | None
    """
    levels = _extract_levels(levels_or_payload)
    if not levels:
        return None

    items: List[Tuple[str, float]] = sorted(levels.items(), key=lambda x: x[1])
    best: Optional[Dict[str, object]] = None
    n = len(items)

    for i in range(n):
        cluster: List[Tuple[str, float]] = [items[i]]
        for j in range(i + 1, n):
            tmp = cluster + [items[j]]
            prices = [p for _, p in tmp]
            center = sum(prices) / len(prices)
            if center == 0:
                break
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
                # เลือกจำนวนสมาชิกมากกว่า; ถ้าเท่ากัน เลือก spread แคบกว่า
                if len(cluster) > len(best["members"]):
                    best = cand
                elif len(cluster) == len(best["members"]) and cand["spread_pct"] < best["spread_pct"]:
                    best = cand

    return best
