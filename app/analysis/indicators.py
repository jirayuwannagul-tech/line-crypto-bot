"""
Indicators Layer (interfaces + stubs, no heavy math yet)

กลุ่มที่รองรับ (เริ่มต้น):
- Trend: SMA, EMA, WMA, HMA, ADX, Ichimoku
- Momentum: RSI, Stochastic, MACD, ROC, MFI
- Volatility: Bollinger Bands (BB), ATR, Keltner
- Volume: OBV, VWAP
- Others: CCI, Pivot Points, Parabolic SAR

สัญญา I/O:
- รับ Series (symbol, timeframe, candles[open,high,low,close,volume,ts])
- คืนค่ารูปแบบ dict/obj ตามชนิดตัวชี้วัด (ดูฟังก์ชันแต่ละตัว)
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Literal, TypedDict

# ── Try import from project schemas; if not available, define fallbacks ──
try:
    from app.schemas.series import Series  # expected: symbol, timeframe, candles(list)
except Exception:
    class Candle(TypedDict, total=False):
        open: float; high: float; low: float; close: float
        volume: float; ts: int
    class Series(TypedDict):
        symbol: str
        timeframe: str
        candles: List[Candle]

# Optional: try importing typed params/results (ไม่จำเป็นต่อการรัน stub)
try:
    from app.schemas.indicators import (
        RSIParams, RSIResult,
        MACDParams, MACDResult,
        BBParams, BBResult,
        ATRParams, ATRResult,
    )
except Exception:
    # Lightweight fallbacks
    PriceSource = Literal["close", "hl2", "hlc3", "ohlc4"]
    class RSIParams(TypedDict, total=False):
        length: int
        source: PriceSource
    class RSIResult(TypedDict, total=False):
        value: Optional[float]
    class MACDParams(TypedDict, total=False):
        fast: int; slow: int; signal: int; source: PriceSource
    class MACDResult(TypedDict, total=False):
        macd: Optional[float]; signal: Optional[float]; hist: Optional[float]
    class BBParams(TypedDict, total=False):
        length: int; mult: float; source: PriceSource
    class BBResult(TypedDict, total=False):
        basis: Optional[float]; upper: Optional[float]; lower: Optional[float]; width: Optional[float]
    class ATRParams(TypedDict, total=False):
        length: int
    class ATRResult(TypedDict, total=False):
        value: Optional[float]

# ── helpers ──
def _pick_source(candle: Dict[str, float], source: str = "close") -> float:
    if source == "close":
        return float(candle["close"])
    if source == "hl2":
        return (float(candle["high"]) + float(candle["low"])) / 2.0
    if source == "hlc3":
        return (float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3.0
    if source == "ohlc4":
        return (float(candle["open"]) + float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 4.0
    return float(candle["close"])

def _last_price(series: Series, source: str = "close") -> Optional[float]:
    if not series.get("candles"):
        return None
    return _pick_source(series["candles"][-1], source)

# ─────────────────────────  Momentum  ───────────────────────── #

def rsi(series: Series, params: Optional[RSIParams] = None) -> RSIResult:
    """
    Return: {'value': float|None}
    NOTE: stub → คืน None จนกว่าจะเติมสูตร
    """
    return {"value": None}

def macd(series: Series, params: Optional[MACDParams] = None) -> MACDResult:
    """
    Return: {'macd': float|None, 'signal': float|None, 'hist': float|None}
    """
    return {"macd": None, "signal": None, "hist": None}

def roc(series: Series, length: int = 10, source: str = "close") -> Optional[float]:
    """Rate of Change (%)."""
    return None

def stochastic(series: Series, k: int = 14, d: int = 3, smooth: int = 3) -> Dict[str, Optional[float]]:
    """Return {'k': float|None, 'd': float|None}."""
    return {"k": None, "d": None}

def mfi(series: Series, length: int = 14) -> Optional[float]:
    """Money Flow Index (0..100)."""
    return None

# ─────────────────────────  Trend  ───────────────────────── #

def sma(series: Series, length: int = 20, source: str = "close") -> Optional[float]:
    return None

def ema(series: Series, length: int = 20, source: str = "close") -> Optional[float]:
    return None

def wma(series: Series, length: int = 20, source: str = "close") -> Optional[float]:
    return None

def hma(series: Series, length: int = 20, source: str = "close") -> Optional[float]:
    return None

def adx(series: Series, length: int = 14) -> Dict[str, Optional[float]]:
    """Return {'adx': float|None, '+di': float|None, '-di': float|None}."""
    return {"adx": None, "+di": None, "-di": None}

def ichimoku(series: Series, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52) -> Dict[str, Optional[float]]:
    """Return {'tenkan','kijun','senkou_a','senkou_b','chikou'}."""
    return {"tenkan": None, "kijun": None, "senkou_a": None, "senkou_b": None, "chikou": None}

# ────────────────────────  Volatility  ─────────────────────── #

def bollinger_bands(series: Series, params: Optional[BBParams] = None) -> BBResult:
    """
    Return: {'basis','upper','lower','width'} (all float|None)
    """
    return {"basis": None, "upper": None, "lower": None, "width": None}

def atr(series: Series, params: Optional[ATRParams] = None) -> ATRResult:
    """Return: {'value': float|None}."""
    return {"value": None}

def keltner(series: Series, ema_length: int = 20, atr_length: int = 10, atr_mult: float = 1.5) -> Dict[str, Optional[float]]:
    """Return {'basis','upper','lower','width'} using ATR channel logic."""
    return {"basis": None, "upper": None, "lower": None, "width": None}

# ─────────────────────────  Volume   ───────────────────────── #

def obv(series: Series) -> Optional[float]:
    return None

def vwap(series: Series, session_reset: Literal["daily","none"] = "daily") -> Optional[float]:
    return None

# ────────────────────────  Others  ─────────────────────────── #

def cci(series: Series, length: int = 20) -> Optional[float]:
    return None

def pivot_points(last_candle: Dict[str, float], mode: Literal["classic","fibonacci","camarilla"] = "classic") -> Dict[str, Optional[float]]:
    """
    Input: last_candle (ใช้ H/L/C ของคาบก่อนหน้า)
    Return: {'pp','s1','s2','s3','r1','r2','r3'}
    """
    return {"pp": None, "s1": None, "s2": None, "s3": None, "r1": None, "r2": None, "r3": None}

def parabolic_sar(series: Series, step: float = 0.02, max_step: float = 0.2) -> Optional[float]:
    return None
