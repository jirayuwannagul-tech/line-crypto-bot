"""
Filters Layer (market & signal hygiene)

วัตถุประสงค์:
- คัดสัญญาณลวงออกด้วยเงื่อนไขขั้นต่ำของตลาด
- ใช้ก่อนจะตัดสินใจใน strategies เพื่อคุมคุณภาพ

ฟิลเตอร์ที่รองรับ (เริ่มต้น):
- Trend filter        → เทรนด์ชัดพอหรือไม่ (EMA slope, ADX ฯลฯ)
- Volatility filter   → ATR/price ขั้นต่ำ (ตลาดนิ่งเกินไปให้ข้าม)
- Session filter      → ช่วงเวลาที่อนุญาต (Asia/EU/US/24-7)
- Volume filter       → วอลุ่มขั้นต่ำ (เช่น เทียบค่าเฉลี่ย N คาบ)
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Literal

try:
    from app.schemas.series import Series
except Exception:
    from typing import TypedDict
    class Candle(TypedDict, total=False):
        open: float; high: float; low: float; close: float
        volume: float; ts: int
    class Series(TypedDict):
        symbol: str
        timeframe: str
        candles: List[Candle]

# ────────────────────────────── Filters ───────────────────────────── #

def trend_filter(series: Series, min_strength: float = 0.5) -> bool:
    """
    True = เทรนด์ชัดพอ / False = ยังไม่ชัด
    หมายเหตุ: stub → คืน True ไปก่อน
    """
    return True

def volatility_filter(series: Series, min_atr_pct: float = 0.005) -> bool:
    """
    True = ความผันผวนพอ / False = นิ่งเกินไป
    """
    return True

def session_filter(ts_ms: Optional[int], allowed: Literal["asia","eu","us","24/7"] = "24/7") -> bool:
    """
    ตรวจเวลา/เซสชันที่อนุญาต (ต้องไปแมปใน utils.time_tools)
    """
    return True

def volume_filter(series: Series, min_multiple_of_avg: float = 1.0, lookback: int = 20) -> bool:
    """
    True = วอลุ่มตอนนี้ >= min_multiple * ค่าเฉลี่ย
    """
    return True
