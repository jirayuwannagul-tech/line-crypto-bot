from __future__ import annotations

# TF เริ่มต้น
TFS_DEFAULT = ("5M", "15M", "30M")

# น้ำหนักแต่ละ TF (ถ่วงสรุป)
WEIGHTS = {"30M": 3, "15M": 2, "5M": 1}

# เกณฑ์ความผันผวนขั้นต่ำ (ATR% ของราคา)
VOL_MIN = {"5M": 0.0010, "15M": 0.0015, "30M": 0.0020}  # ~0.10/0.15/0.20%

# ถือว่า ema50≈ema200 ถ้าต่างกันไม่เกิน 0.10%
NEAR_EPS = 0.0010

# จำนวนแท่งขั้นต่ำ/จำนวนแท่งล่าสุดที่ใช้คำนวณ
MIN_BARS = 220
TAIL = 800

__all__ = ["TFS_DEFAULT", "WEIGHTS", "VOL_MIN", "NEAR_EPS", "MIN_BARS", "TAIL"]
