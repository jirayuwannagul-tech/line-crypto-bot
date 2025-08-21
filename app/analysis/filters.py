# PATCH: replace stub functions with minimal working logic

from __future__ import annotations
from typing import Optional, Dict, Any, List, Literal
import math

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

def _to_df(series: Series):
    import pandas as pd
    df = pd.DataFrame(series.get("candles", []))
    # ป้องกันค่าว่าง/เรียงเวลา
    for c in ("open","high","low","close","volume"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    if "ts" in df.columns:
        df = df.sort_values("ts")
    return df.dropna(subset=["open","high","low","close"])

def _ema(s, n):
    import pandas as pd
    s = pd.to_numeric(s, errors="coerce")
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

def _atr_pct(df, n=14):
    import pandas as pd, numpy as np
    if len(df) < n+1: return None
    h,l,c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h-l).abs(), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    last_close = float(c.iloc[-1])
    if last_close == 0 or math.isnan(last_close): return None
    return float(atr.iloc[-1] / last_close)

def trend_filter(series: Series, min_strength: float = 0.0) -> bool:
    """
    โครงสร้างเทรนด์แบบง่าย: close>ema200 และ ema50>ema200 (bull) หรือกลับทิศ (bear)
    คืน True ถ้าอย่างน้อยมี 'ทิศ' ที่ชัด; ไม่บังคับแรงขั้นต่ำ
    """
    df = _to_df(series)
    if len(df) < 200:  # ข้อมูลสั้นมาก ถือว่าไม่ผ่าน
        return False
    ema50 = _ema(df["close"], 50).iloc[-1]
    ema200 = _ema(df["close"], 200).iloc[-1]
    last = float(df["close"].iloc[-1])
    if any(map(lambda x: x is None or math.isnan(x), (ema50, ema200, last))):
        return False
    bull = last > ema200 and ema50 > ema200
    bear = last < ema200 and ema50 < ema200
    return bool(bull or bear)

def volatility_filter(series: Series, min_atr_pct: float = 0.005) -> bool:
    """
    ใช้ ATR% ล่าสุด เทียบเกณฑ์ (เช่น >=0.5%)
    """
    df = _to_df(series)
    atrp = _atr_pct(df, n=14)
    if atrp is None: return False
    return atrp >= float(min_atr_pct)

def session_filter(ts_ms: Optional[int], allowed: Literal["asia","eu","us","24/7"] = "24/7") -> bool:
    """
    MVP: อนุญาต 24/7 ไปก่อน (คริปโต)
    """
    return allowed == "24/7"

def volume_filter(series: Series, min_multiple_of_avg: float = 1.0, lookback: int = 20) -> bool:
    """
    วอลุ่มแท่งล่าสุด >= avg(lookback) * k
    """
    import pandas as pd
    df = _to_df(series)
    if len(df) < lookback+1: return False
    v = pd.to_numeric(df["volume"], errors="coerce")
    avg = v.rolling(lookback, min_periods=lookback).mean().iloc[-1]
    if avg is None or math.isnan(avg): return False
    return float(v.iloc[-1]) >= float(avg) * float(min_multiple_of_avg)
