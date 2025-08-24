# app/logic/elliott_logic.py
# ============================================================
# Elliott Logic Layer
# - เชื่อม analysis.elliott (rules) ↔ scenarios (integration)
# - ทำหน้าที่: แปลงผลจาก rules → output ที่ scenarios ใช้ได้
# ============================================================

from __future__ import annotations
from typing import Dict, Any
import pandas as pd

# ✅ เรียกใช้ rules จาก analysis (กฎคงเดิม)
from app.analysis.elliott import analyze_elliott_rules
# ✅ ใช้อินดิเคเตอร์เป็นบริบท (ไม่แก้กฎ)
from app.analysis.indicators import apply_indicators


def _context(df: pd.DataFrame) -> Dict[str, float]:
    """
    สร้างบริบทเทรนด์จากอินดิเคเตอร์พื้นฐาน (ไม่ผูกช่วงเวลา)
    """
    try:
        ctx = apply_indicators(df.copy(), ema_windows=[20, 50], rsi_window=14, atr_window=14)
        ema20 = float(ctx["ema_20"].iloc[-1])
        ema20_prev = float(ctx["ema_20"].iloc[-4]) if len(ctx) >= 4 else float(ctx["ema_20"].iloc[-1])
        rsi = float(ctx["rsi_14"].iloc[-1]) if "rsi_14" in ctx else 50.0
        atr = float(ctx["atr_14"].iloc[-1]) if "atr_14" in ctx else 0.0
        close = float(df["close"].iloc[-1])
        ema_slope = ema20 - ema20_prev
        atr_pct = atr / max(close, 1e-9)
        direction = "up" if ema_slope > 0 else ("down" if ema_slope < 0 else "side")
        return {"ema_slope": ema_slope, "rsi": rsi, "atr_pct": atr_pct, "direction": direction}
    except Exception:
        # fallback เบื้องต้นกรณีอินดิเคเตอร์คำนวณไม่ได้
        if len(df) >= 2:
            close, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
            ema_slope = close - prev
            direction = "up" if ema_slope > 0 else ("down" if ema_slope < 0 else "side")
        else:
            ema_slope, direction = 0.0, "side"
        return {"ema_slope": ema_slope, "rsi": 50.0, "atr_pct": 0.0, "direction": direction}


def _score(pattern: str, rules: list, ctx: Dict[str, float]) -> float:
    """
    ให้คะแนนจากกฎที่ผ่าน + บริบทเทรนด์ (พื้นฐานทั่วไป ใช้กับกราฟจริง)
    """
    total = max(len(rules), 1)
    base = sum(1 for r in rules if r.get("passed")) / total

    trend = 0.0
    # เทรนด์ชัดช่วยยืนยันโครงสร้างคลื่นที่กำลังก้าวหน้า (progress)
    if ctx["ema_slope"] > 0 and ctx["rsi"] >= 55:
        trend += 0.25
    if ctx["ema_slope"] < 0 and ctx["rsi"] <= 45:
        trend += 0.25
    # ความผันผวนสูง ลดความเชื่อมั่นเล็กน้อย
    if ctx["atr_pct"] > 0.05:
        trend -= 0.15

    s = max(0.0, min(1.0, base + trend))
    return s


def classify_elliott(df: pd.DataFrame) -> Dict[str, Any]:
    """
    ตีความผลลัพธ์จาก analyze_elliott_rules → payload ที่ scenarios ใช้ได้
    - ไม่แก้กฎ
    - ใช้บริบทช่วยตัดสินใจเพื่อกราฟจริงในอนาคต
    """
    try:
        res = analyze_elliott_rules(df, pivot_left=2, pivot_right=2)
    except Exception:
        return {
            "pattern": "UNKNOWN",
            "completed": False,
            "current": {"direction": "side"},
            "targets": {},
        }

    patt = res.get("pattern", "UNKNOWN")
    rules = res.get("rules", [])
    debug = res.get("debug", {})

    # บริบทเทรนด์ทั่วไป
    ctx = _context(df)
    direction = ctx["direction"]

    # ให้คะแนนความเชื่อมั่น
    s = _score(patt, rules, ctx)

    # Post-interpretation (ไม่แตะกฎ):
    # 1) ถ้า UNKNOWN แต่บริบทหนุนพอ → ยกเป็น IMPULSE (progress)
    if patt == "UNKNOWN" and s >= 0.55:
        patt = "IMPULSE"

    # 2) สถานะ completed: ใช้บริบทยืนยันการชะลอ/กลับทิศ
    completed = False
    if patt in ("IMPULSE", "DIAGONAL", "ZIGZAG", "FLAT", "TRIANGLE"):
        # ถือว่าจบคลื่นเมื่อคะแนนสูงพอ + RSI/EMA สวนทิศปัจจุบัน (สัญญาณชะลอ)
        if s >= 0.70 and (
            (direction == "up" and ctx["rsi"] < 50 and ctx["ema_slope"] <= 0) or
            (direction == "down" and ctx["rsi"] > 50 and ctx["ema_slope"] >= 0)
        ):
            completed = True

    return {
        "pattern": patt,
        "completed": completed,
        "current": {
            "direction": direction,
            "rsi": ctx["rsi"],
            "ema20_slope": ctx["ema_slope"],
            "atr_pct": ctx["atr_pct"],
            "confidence": s,
        },
        "targets": {},  # (เผื่อเติม fib/projection ภายหลัง)
        "rules": rules,
        "debug": debug,
    }
