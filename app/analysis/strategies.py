"""
Strategies Layer
รวมผล indicators + patterns + filters → สร้าง 'สัญญาณเบื้องต้น'
(Engine จะนำผลนี้ไปคำนวน Entry/SL/TP และ no-flip ต่อ)

สัญญา Output (pre-signal):
{
  'symbol': str,
  'timeframe': str,
  'long_score': float,     # 0..1
  'short_score': float,    # 0..1
  'bias': 'long'|'short'|'neutral',
  'reasons': [ { 'code': str, 'message': str, 'weight': float, 'meta': {...} }, ... ],
  'strategy_id': str
}
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Literal

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

# นำเข้าชั้นวิเคราะห์ (stub จะคืนค่า None/False/0.0 ตามที่กำหนด)
from . import indicators as ind
from . import patterns as pat
from . import filters as flt

def _reason(code: str, message: str, weight: float, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "weight": float(weight), "meta": meta or {}}

def _decide_bias(long_score: float, short_score: float, threshold: float = 0.6) -> Literal["long","short","neutral"]:
    if long_score >= threshold and long_score > short_score:
        return "long"
    if short_score >= threshold and short_score > long_score:
        return "short"
    return "neutral"

# ─────────────────────── กลยุทธ์ตัวอย่าง (MVP) ─────────────────────── #

def momentum_breakout(series: Series, strategy_id: str = "momentum_breakout") -> Dict[str, Any]:
    """
    แนวคิด:
    - ต้องผ่าน Filters พื้นฐานก่อน (trend, volatility, session)
    - มองหาการ 'บีบ' (BB) + เบรกระดับ (breakout) + ยืนยันด้วย RSI/MACD
    - รวมคะแนนแต่ละเงื่อนไขด้วยน้ำหนักง่าย ๆ (จะไปย้ายค่าน้ำหนักจาก config ภายหลัง)

    NOTE: ไฟล์นี้เป็น stub → ยังไม่อ่านค่า indicators จริง (จะคืนคะแนนเบื้องต้น 0.0 ทั้งคู่)
    """
    reasons: List[Dict[str, Any]] = []
    long_score = 0.0
    short_score = 0.0

    # ── Filters (ผ่านก่อนค่อยคิดคะแนน) ──
    if not flt.trend_filter(series):
        reasons.append(_reason("FILTER_TREND_FAIL", "trend ไม่ชัดพอ", 0.0))
        return {
            "symbol": series.get("symbol", ""),
            "timeframe": series.get("timeframe", ""),
            "long_score": 0.0,
            "short_score": 0.0,
            "bias": "neutral",
            "reasons": reasons,
            "strategy_id": strategy_id,
        }

    if not flt.volatility_filter(series):
        reasons.append(_reason("FILTER_VOL_FAIL", "volatility ไม่พอ", 0.0))
        return {
            "symbol": series.get("symbol", ""),
            "timeframe": series.get("timeframe", ""),
            "long_score": 0.0,
            "short_score": 0.0,
            "bias": "neutral",
            "reasons": reasons,
            "strategy_id": strategy_id,
        }

    # ── Patterns ──
    brk = pat.detect_breakout(series, lookback=20)
    if brk and brk.get("is_valid"):
        # ตัวอย่างน้ำหนัก (จะย้ายไป config ในเวอร์ชันถัดไป)
        reasons.append(_reason("BRK_OK", "พบสัญญาณ breakout", 0.3, brk.get("meta")))
        # long_score += 0.3  # TODO: หลังเติม logic จริงค่อยให้คะแนน
        pass

    ib = pat.detect_inside_bar(series)
    if ib and ib.get("is_valid"):
        reasons.append(_reason("IB_OK", "พบ inside bar น่าสนใจ", 0.1, ib.get("meta")))
        # long_score += 0.1
        pass

    # ── Indicators (stubs) ──
    rsi_res = ind.rsi(series, params={"length": 14, "source": "close"})  # stub returns {'value': None}
    macd_res = ind.macd(series, params={"fast": 12, "slow": 26, "signal": 9, "source": "close"})

    if rsi_res.get("value") is not None:
        val = float(rsi_res["value"])
        if val > 50:
            reasons.append(_reason("RSI_GT_50", "RSI > 50", 0.2, {"rsi": val}))
            # long_score += 0.2
        elif val < 50:
            reasons.append(_reason("RSI_LT_50", "RSI < 50", 0.2, {"rsi": val}))
            # short_score += 0.2

    if macd_res.get("hist") is not None:
        hist = float(macd_res["hist"])
        if hist > 0:
            reasons.append(_reason("MACD_POS", "MACD histogram > 0", 0.2, {"hist": hist}))
            # long_score += 0.2
        elif hist < 0:
            reasons.append(_reason("MACD_NEG", "MACD histogram < 0", 0.2, {"hist": hist}))
            # short_score += 0.2

    # ── Elliott (optional) ──
    # ew = pat.detect_elliott_wave(series)
    # if ew and ew.get("is_valid"):
    #     reasons.append(_reason("EW_OK", "Elliott structure สนับสนุน", 0.2, ew.get("meta")))
    #     # long_score += 0.2  # หรือ short_score ตามโครงสร้าง

    bias = _decide_bias(long_score, short_score, threshold=0.6)
    return {
        "symbol": series.get("symbol", ""),
        "timeframe": series.get("timeframe", ""),
        "long_score": float(long_score),
        "short_score": float(short_score),
        "bias": bias,
        "reasons": reasons,
        "strategy_id": strategy_id,
    }

# ─────────────────────── จุดขยายเพิ่มกลยุทธ์ ─────────────────────── #

def trend_pullback(series: Series, strategy_id: str = "trend_pullback") -> Dict[str, Any]:
    """
    ไอเดีย:
    - ต้องมีเทรนด์ (EMA/ADX)
    - รอรีเทส EMA/VWAP แล้วเกิด rejection
    - ยืนยันด้วย RSI (อยู่เหนือ/ใต้ 50) หรือ MACD
    """
    return {
        "symbol": series.get("symbol", ""),
        "timeframe": series.get("timeframe", ""),
        "long_score": 0.0,
        "short_score": 0.0,
        "bias": "neutral",
        "reasons": [],
        "strategy_id": strategy_id,
    }

def mean_reversion(series: Series, strategy_id: str = "mean_reversion") -> Dict[str, Any]:
    """
    ไอเดีย:
    - ราคาออกนอกแบนด์ (BB) + RSI extreme
    - วอลุ่มไม่สนับสนุนเทรนด์ → เด้งกลับเข้า mean
    """
    return {
        "symbol": series.get("symbol", ""),
        "timeframe": series.get("timeframe", ""),
        "long_score": 0.0,
        "short_score": 0.0,
        "bias": "neutral",
        "reasons": [],
        "strategy_id": strategy_id,
    }
