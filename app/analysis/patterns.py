"""
Patterns Layer (detectors + stubs, no heavy math yet)

ครอบคลุม:
- Inside Bar
- Breakout
- Divergence (RSI/MACD/OBV)
- S/R Touch or Rejection
- Elliott Wave (labels, structure, validation, confidence)

ผลลัพธ์มาตรฐานของ detector:
{
  "pattern": str,
  "is_valid": bool,
  "confidence": float,       # 0..1
  "ref_index": int | None,   # จุดอ้างอิง (เช่น แท่งล่าสุด = -1)
  "meta": { ... }            # รายละเอียดเฉพาะของ pattern
}
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

# ─────────────────────── Basic price-patterns ─────────────────────── #

def detect_inside_bar(series: Series) -> Optional[Dict[str, Any]]:
    """
    เงื่อนไข: แท่งล่าสุด (หรือกลุ่มล่าสุด) อยู่ในช่วง H-L ของแท่งก่อนหน้า
    meta: {'range_pct': float|None}
    """
    return {
        "pattern": "inside_bar",
        "is_valid": False,
        "confidence": 0.0,
        "ref_index": -1,
        "meta": {"range_pct": None},
    }

def detect_breakout(series: Series, lookback: int = 20, direction: Literal["auto","up","down"] = "auto") -> Optional[Dict[str, Any]]:
    """
    เงื่อนไข: ทะลุ high/low ของ lookback ล่าสุด
    meta: {'lookback': int, 'level': float|None, 'direction': 'up'|'down'|None, 'retest': bool|None}
    """
    return {
        "pattern": "breakout",
        "is_valid": False,
        "confidence": 0.0,
        "ref_index": -1,
        "meta": {"lookback": lookback, "level": None, "direction": None, "retest": None},
    }

def detect_divergence(series: Series, base: Literal["rsi","macd","obv"] = "rsi") -> Optional[Dict[str, Any]]:
    """
    เงื่อนไข: ราคา vs indicator ทำ HH/LL ไม่สอดคล้อง
    meta: {'type': 'bull'|'bear'|None, 'swings': list|None}
    """
    return {
        "pattern": "divergence",
        "is_valid": False,
        "confidence": 0.0,
        "ref_index": -1,
        "meta": {"base": base, "type": None, "swings": None},
    }

def detect_sr_touch(series: Series, level: Optional[float] = None, mode: Literal["ema","vwap","pivot","static"] = "ema") -> Optional[Dict[str, Any]]:
    """
    เงื่อนไข: แตะ/ปฏิเสธบริเวณแนวรับ-ต้าน
    meta: {'level': float|None, 'wick_ratio': float|None, 'close_pos': float|None}
    """
    return {
        "pattern": "sr_touch",
        "is_valid": False,
        "confidence": 0.0,
        "ref_index": -1,
        "meta": {"mode": mode, "level": level, "wick_ratio": None, "close_pos": None},
    }

# ─────────────────────────── Elliott Wave ─────────────────────────── #

def detect_elliott_wave(
    series: Series,
    max_depth: int = 3,
    prefer_impulse: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    ตรวจโครงสร้าง Elliott (เบื้องต้น)
    Output:
      {
        'pattern': 'elliott',
        'is_valid': bool,
        'confidence': float,
        'ref_index': -1,
        'meta': {
          'structure': 'impulse'|'corrective'|None,
          'labels': ['1','2','3','4','5'] หรือ ['A','B','C'] หรือ None,
          'fib': {'ratios': {...}} | None,
          'rules_passed': int,
          'rules_total': int
        }
      }
    """
    return {
        "pattern": "elliott",
        "is_valid": False,
        "confidence": 0.0,
        "ref_index": -1,
        "meta": {
            "structure": None,
            "labels": None,
            "fib": {"ratios": None},
            "rules_passed": 0,
            "rules_total": 0,
            "prefer_impulse": bool(prefer_impulse),
            "max_depth": max_depth,
        },
    }
