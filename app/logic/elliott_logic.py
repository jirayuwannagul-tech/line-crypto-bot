# app/logic/elliott_logic.py
# ============================================================
# Elliott Logic Layer
# - เชื่อม analysis.elliott (rules) ↔ scenarios (integration)
# - ทำหน้าที่: แปลงผลจาก rules → output ที่ scenarios ใช้ได้
# ============================================================

from __future__ import annotations
from typing import Dict, Any
import math
import pandas as pd

# ✅ เรียกใช้ rules จาก analysis
from app.analysis.elliott import analyze_elliott_rules


def classify_elliott(df: pd.DataFrame) -> Dict[str, Any]:
    """
    ตีความผลลัพธ์จาก analyze_elliott_rules
    คืน dict ที่ scenarios ใช้ได้ เช่น:
    {
        "pattern": "IMPULSE",
        "current": {"direction": "up"},
        "completed": False,
        "targets": {}
    }
    """
    try:
        res = analyze_elliott_rules(df, pivot_left=2, pivot_right=2)
    except Exception:
        return {"pattern": "UNKNOWN", "completed": False, "current": {"direction": "side"}, "targets": {}}

    patt = res.get("pattern", "UNKNOWN")

    # -------------------------
    # Direction heuristic
    # -------------------------
    direction = "side"
    if len(df) > 1:
        close = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-2])
        if close > prev:
            direction = "up"
        elif close < prev:
            direction = "down"

    # -------------------------
    # Completed heuristic
    # -------------------------
    completed = False
    if patt in ("IMPULSE", "DIAGONAL", "ZIGZAG", "FLAT", "TRIANGLE"):
        completed = True  # กรณีเจอ pattern ที่ match rule

    # -------------------------
    # Payload ให้ scenarios ใช้
    # -------------------------
    return {
        "pattern": patt,
        "completed": completed,
        "current": {"direction": direction},
        "targets": {},       # (optionally เติมฟิโบหรือ projection ได้ในอนาคต)
        "rules": res.get("rules", []),
        "debug": res.get("debug", {}),
    }
