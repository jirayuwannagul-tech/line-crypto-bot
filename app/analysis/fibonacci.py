# app/analysis/fibonacci.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - ฟังก์ชันคำนวณ Fibonacci retracement / extension (คง API เดิม)
# - เพิ่ม "Fibo Cluster" utilities สำหรับหากลุ่มระดับ fib ที่แน่นพอ (ใช้ timing)
# - ใช้ได้ทั้งขาขึ้น/ขาลง; ไม่พึ่งพา external libs นอกเหนือจาก stdlib
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
# LAYER B) CONSTANTS
# -----------------------------------------------------------------------------
# ระดับมาตรฐานที่ใช้บ่อย (คงของเดิม)
# =============================================================================
FIB_RETRACEMENTS: Tuple[float, ...] = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
FIB_EXTENSIONS: Tuple[float, ...]   = (1.272, 1.414, 1.618, 2.0, 2.618, 3.618)

# =============================================================================
# LAYER C) CORE HELPERS
# -----------------------------------------------------------------------------
def _detect_direction(A: Number, B: Number) -> Direction:
    if B > A:
        return "up"
    elif B < A:
        return "down"
    else:
        raise ValueError("A and B must not be equal.")

def _key(r: float) -> str:
    # แปลง ratio เป็นคีย์สวย ๆ เช่น "0.618", "1.272"
    return f"{r:.3f}".rstrip("0").rstrip(".")

# =============================================================================
# LAYER D) PUBLIC API (คงของเดิม + ปรับปรุงภายใน)
# -----------------------------------------------------------------------------
def fib_levels(
    A: Number,
    B: Number,
    ratios: Tuple[float, ...] = FIB_RETRACEMENTS,
) -> Dict[str, object]:
    """
    คำนวณ Fibonacci retracement ระหว่าง A->B
    - ขาขึ้น: ระดับจะอยู่ระหว่าง B ลงไปหา A
    - ขาลง: ระดับจะอยู่ระหว่าง B ขึ้นไปหา A
    Returns:
      {
        "direction": "up" | "down",
        "A": float, "B": float,
        "levels": OrderedDict[str, float]  # key เช่น "0.618"
      }
    """
    A = float(A); B = float(B)
    direction = _detect_direction(A, B)
    diff = B - A

    levels = OrderedDict()
    for r in ratios:
        if direction == "up":
            price = B - (diff * r)
        else:
            price = B + ((A - B) * r)  # เทียบเท่า B - diff*r เมื่อ diff < 0
        levels[_key(r)] = float(price)

    return {"direction": direction, "A": A, "B": B, "levels": levels}

def fib_extensions(
    A: Number,
    B: Number,
    ratios: Tuple[float, ...] = FIB_EXTENSIONS,
) -> Dict[str, object]:
    """
    คำนวณ Fibonacci extension ต่อจากช่วง A->B
    - ขาขึ้น: วัดต่อจาก B ขึ้นไป
    - ขาลง: วัดต่อจาก B ลงไป
    Returns:
      {
        "direction": "up" | "down",
        "A": float, "B": float,
        "levels": OrderedDict[str, float]
      }
    """
    A = float(A); B = float(B)
    direction = _detect_direction(A, B)
    length = abs(B - A)

    levels = OrderedDict()
    for r in ratios:
        if direction == "up":
            price = B + (length * (r - 1.0))
        else:
            price = B - (length * (r - 1.0))
        levels[_key(r)] = float(price)

    return {"direction": direction, "A": A, "B": B, "levels": levels}

# =============================================================================
# LAYER E) FIBO CLUSTER UTILITIES
# -----------------------------------------------------------------------------
# อธิบาย:
# - Fibo "cluster" = กลุ่มระดับราคาหลายตัว (จาก retr/extension หลายช่วง)
#   ที่อยู่ใกล้กันมาก (เช่น ภายใน ±0.3% ของราคาเฉลี่ย) → ใช้เป็นโซนกลับตัว/ทำกำไร
# - ใช้กับโปรไฟล์:
#     - chinchot: อนุญาตเข้าเร็วเมื่อเข้าใกล้ cluster
#     - cholak : ใช้ cluster เป็น confirm zone ร่วมกับ EMA/RSI
# -----------------------------------------------------------------------------
def merge_levels(*level_dicts: Dict[str, float]) -> Dict[str, float]:
    """
    รวม OrderedDict ของ fib levels หลายชุดเป็น dict เดียว:
      merge_levels(retr["levels"], ext["levels"], ...)
    ถ้าคีย์ซ้ำจะเก็บอันหลังสุด (ไม่มีผลต่อ cluster เพราะใช้ 'ค่า' เป็นหลัก)
    """
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
    ตรวจหา "คลัสเตอร์" ของระดับ fib ที่อยู่ใกล้กันภายใน tolerance_pct
    Parameters
    ----------
    levels : dict[str, float]
        แผนที่คีย์→ราคา (เช่น {"0.5": 43210.0, "0.618": 42890.0, "1.272": 43880.0})
    tolerance_pct : float
        ระยะห่างสัมพัทธ์สูงสุดจากค่าเฉลี่ยของกลุ่ม เช่น 0.003 = 0.3%
    min_points : int
        จำนวนระดับขั้นต่ำในคลัสเตอร์หนึ่ง (ปกติ ≥2)

    Returns
    -------
    {
      "center": float,              # ราคาเฉลี่ยของคลัสเตอร์
      "members": List[Tuple[key,price]],
      "spread_pct": float           # สัดส่วนกว้างสุดของคลัสเตอร์ต่อราคา center
    } | None
    """
    if not levels:
        return None
    # เรียงตามราคาเพื่อสแกนหาระยะประชิด
    items = sorted(((k, float(v)) for k, v in levels.items()), key=lambda x: x[1])
    best: Optional[Dict[str, object]] = None

    # สไลด์วินโดว์ทุกคู่เริ่มต้น แล้วขยายจนกว่าจะเกิน tolerance
    n = len(items)
    for i in range(n):
        cluster: List[Tuple[str, float]] = [items[i]]
        # ขยาย
        for j in range(i+1, n):
            tmp = cluster + [items[j]]
            prices = [p for _, p in tmp]
            center = sum(prices) / len(prices)
            # วัด max deviation จาก center
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
            # เลือกคลัสเตอร์ที่ "แน่น" กว่า หรือมีสมาชิกมากกว่า
            if best is None:
                best = cand
            else:
                if len(cluster) > len(best["members"]):  # สมาชิกมากกว่ามีสิทธิ์ก่อน
                    best = cand
                elif len(cluster) == len(best["members"]) and cand["spread_pct"] < best["spread_pct"]:
                    best = cand
    return best
