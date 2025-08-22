# app/analysis/patterns.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - ตรวจจับ "Pattern" ที่เกิดขึ้นจากราคา
# - รองรับทั้ง Elliott wave (โครงสร้างคลื่น 1-5 / A-B-C)
# - และ basic chart patterns (triangle, flat, zigzag)
# - ใช้ข้อมูลจาก Series (candles) แล้วคืนค่า dict ของ pattern ที่ตรวจพบ
# =============================================================================

from __future__ import annotations
from typing import Dict, Any, List, Optional

try:
    from app.schemas.series import Series
except Exception:
    from typing import TypedDict
    class Candle(TypedDict, total=False):
        open: float; high: float; low: float; close: float; volume: float; ts: int
    class Series(TypedDict):
        symbol: str
        timeframe: str
        candles: List[Candle]

import math

# =============================================================================
# LAYER B) LOW-LEVEL HELPERS
# -----------------------------------------------------------------------------
# ฟังก์ชันคำนวณ swing high/low และ slope สำหรับใช้วิเคราะห์ pattern
# =============================================================================

def _swing_points(candles: List[Dict[str, Any]], lookback: int = 5) -> List[Dict[str, Any]]:
    """
    หา swing high/low จากชุดแท่งเทียนแบบง่าย:
    - swing high: high[i] > high[i-lookback..i+lookback]
    - swing low:  low[i]  < low[i-lookback..i+lookback]
    """
    swings: List[Dict[str, Any]] = []
    for i in range(lookback, len(candles) - lookback):
        high = candles[i]["high"]; low = candles[i]["low"]
        window = candles[i - lookback : i + lookback + 1]
        if high == max(c["high"] for c in window):
            swings.append({"type": "high", "price": high, "idx": i, "ts": candles[i]["ts"]})
        if low == min(c["low"] for c in window):
            swings.append({"type": "low", "price": low, "idx": i, "ts": candles[i]["ts"]})
    return swings

def _slope(p1: Dict[str, Any], p2: Dict[str, Any]) -> float:
    """คำนวณ slope ของเส้นเชื่อมระหว่างจุดสองจุด"""
    if p2["idx"] == p1["idx"]:
        return 0.0
    return (p2["price"] - p1["price"]) / (p2["idx"] - p1["idx"])

# =============================================================================
# LAYER C) PATTERN DETECTORS
# -----------------------------------------------------------------------------
# ตรวจจับ Elliott wave, Zigzag, Flat, Triangle
# =============================================================================

def detect_elliott(series: Series, *, max_swings: int = 9) -> Dict[str, Any]:
    """
    ตรวจจับ Elliott wave แบบง่าย:
    - หา swing points
    - เลือก 5 หรือ 7 จุดล่าสุดมาตีความว่าเป็น impulsive (1-5) หรือ corrective (ABC)
    - คืนค่า dict ที่มี 'pattern' และ 'points'
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, lookback=3)
    if len(swings) < 5:
        return {"pattern": None, "points": []}

    last_swings = swings[-max_swings:]
    labels: List[str] = []

    if len(last_swings) >= 5:
        # สมมุติว่า 5 จุดเป็น wave 1-5
        labels = ["1", "2", "3", "4", "5"]
    elif len(last_swings) >= 3:
        # สมมุติว่า 3 จุดเป็น A-B-C
        labels = ["A", "B", "C"]

    points = [{"label": lbl, "price": pt["price"], "ts": pt["ts"]} 
              for lbl, pt in zip(labels, last_swings)]
    return {"pattern": "elliott", "points": points}

def detect_triangle(series: Series) -> Dict[str, Any]:
    """
    ตรวจจับ Triangle pattern แบบง่าย:
    - ใช้ swing high/low 4 จุดล่าสุด
    - ถ้า slope ของ high เป็นขาลง และ slope ของ low เป็นขาขึ้น → Triangle
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, lookback=3)
    if len(swings) < 4:
        return {"pattern": None, "points": []}

    highs = [s for s in swings if s["type"] == "high"][-2:]
    lows = [s for s in swings if s["type"] == "low"][-2:]

    if len(highs) == 2 and len(lows) == 2:
        slope_highs = _slope(highs[0], highs[1])
        slope_lows = _slope(lows[0], lows[1])
        if slope_highs < 0 and slope_lows > 0:
            return {"pattern": "triangle", "points": highs + lows}

    return {"pattern": None, "points": []}

def detect_zigzag(series: Series) -> Dict[str, Any]:
    """
    ตรวจจับ Zigzag pattern:
    - ดู swing 3 จุดล่าสุด ถ้าสลับสูง-ต่ำ-สูง หรือ ต่ำ-สูง-ต่ำ → Zigzag
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, lookback=3)
    if len(swings) < 3:
        return {"pattern": None, "points": []}

    last3 = swings[-3:]
    types = [pt["type"] for pt in last3]
    if types in (["high","low","high"], ["low","high","low"]):
        return {"pattern": "zigzag", "points": last3}
    return {"pattern": None, "points": []}

def detect_flat(series: Series) -> Dict[str, Any]:
    """
    ตรวจจับ Flat pattern:
    - ถ้าสวิง 3 จุดล่าสุดเป็น low-high-low และ ระยะทางของสอง low ใกล้เคียง → Flat
    """
    candles = series.get("candles", [])
    swings = _swing_points(candles, lookback=3)
    if len(swings) < 3:
        return {"pattern": None, "points": []}

    last3 = swings[-3:]
    types = [pt["type"] for pt in last3]
    if types == ["low","high","low"]:
        low1, _, low2 = last3
        if abs(low2["price"] - low1["price"]) / low1["price"] < 0.02:  # 2% tolerance
            return {"pattern": "flat", "points": last3}
    return {"pattern": None, "points": []}

# =============================================================================
# LAYER D) AGGREGATOR
# -----------------------------------------------------------------------------
# รวมทุก pattern detector แล้วคืนผลลัพธ์เดียว
# =============================================================================

def detect_patterns(series: Series) -> Dict[str, Any]:
    detectors = [detect_elliott, detect_triangle, detect_zigzag, detect_flat]
    results: List[Dict[str, Any]] = []
    for det in detectors:
        res = det(series)
        if res["pattern"]:
            results.append(res)
    return {"patterns": results}
