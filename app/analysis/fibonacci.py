# app/analysis/fibonacci.py
from __future__ import annotations

from typing import Dict, List, Literal, Tuple
from collections import OrderedDict

Number = float
Direction = Literal["up", "down"]

__all__ = [
    "fib_levels",
    "fib_extensions",
    "FIB_RETRACEMENTS",
    "FIB_EXTENSIONS",
]

# มาตรฐานที่ใช้บ่อย
FIB_RETRACEMENTS: Tuple[float, ...] = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
FIB_EXTENSIONS: Tuple[float, ...]   = (1.272, 1.414, 1.618, 2.0, 2.618, 3.618)


def _detect_direction(A: Number, B: Number) -> Direction:
    if B > A:
        return "up"
    elif B < A:
        return "down"
    else:
        raise ValueError("A and B must not be equal.")


def fib_levels(
    A: Number,
    B: Number,
    ratios: Tuple[float, ...] = FIB_RETRACEMENTS,
) -> Dict[str, object]:
    """
    คำนวณ Fibonacci retracement levels ระหว่างจุด A -> B
    รองรับทั้งขาขึ้น (B > A) และขาลง (B < A)

    Returns
    -------
    {
      "direction": "up" | "down",
      "A": float,
      "B": float,
      "levels": OrderedDict[str, float]  # คีย์เช่น "0.618", "0.5", ...
    }
    """
    A = float(A)
    B = float(B)
    direction = _detect_direction(A, B)
    diff = B - A

    levels = OrderedDict()
    # ขาขึ้น: ระดับจะอยู่ระหว่าง B ลงไปหา A
    # ขาลง: ระดับจะอยู่ระหว่าง B ขึ้นไปหา A (กลับทิศ)
    for r in ratios:
        if direction == "up":
            price = B - (diff * r)
        else:
            price = B + ((A - B) * r)  # เทียบเท่า: B - diff*r เพราะ diff < 0
        levels[f"{r:.3f}".rstrip("0").rstrip(".")] = float(price)

    return {
        "direction": direction,
        "A": A,
        "B": B,
        "levels": levels,
    }


def fib_extensions(
    A: Number,
    B: Number,
    ratios: Tuple[float, ...] = FIB_EXTENSIONS,
) -> Dict[str, object]:
    """
    คำนวณ Fibonacci extension levels ต่อจากช่วง A -> B
    - ขาขึ้น: วัดต่อจาก B ขึ้นไป (เหนือ B)
    - ขาลง: วัดต่อจาก B ลงไป (ต่ำกว่า B)

    Returns
    -------
    {
      "direction": "up" | "down",
      "A": float,
      "B": float,
      "levels": OrderedDict[str, float]
    }
    """
    A = float(A)
    B = float(B)
    direction = _detect_direction(A, B)
    length = abs(B - A)

    levels = OrderedDict()
    for r in ratios:
        if direction == "up":
            price = B + (length * (r - 1.0))
        else:
            price = B - (length * (r - 1.0))
        levels[f"{r:.3f}".rstrip("0").rstrip(".")] = float(price)

    return {
        "direction": direction,
        "A": A,
        "B": B,
        "levels": levels,
    }
