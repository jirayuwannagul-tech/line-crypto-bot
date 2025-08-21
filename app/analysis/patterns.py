# PATCH: implement minimal detectors

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

def _to_df(series: Series):
    import pandas as pd
    df = pd.DataFrame(series.get("candles", []))
    for c in ("open","high","low","close","volume"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    if "ts" in df.columns:
        df = df.sort_values("ts")
    return df.dropna(subset=["open","high","low","close"])

def detect_inside_bar(series: Series) -> Optional[Dict[str, Any]]:
    df = _to_df(series)
    if len(df) < 2:
        return None
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    inside = (cur["high"] <= prev["high"]) and (cur["low"] >= prev["low"])
    rng_pct = float((prev["high"] - prev["low"]) / prev["close"]) if prev["close"] else None
    return {
        "pattern": "inside_bar",
        "is_valid": bool(inside),
        "confidence": 0.6 if inside else 0.0,
        "ref_index": -1,
        "meta": {"range_pct": rng_pct},
    }

def detect_breakout(series: Series, lookback: int = 20, direction: Literal["auto","up","down"] = "auto") -> Optional[Dict[str, Any]]:
    df = _to_df(series)
    if len(df) < lookback+1:
        return None
    sub = df.iloc[-(lookback+1):-1]
    level_high = float(sub["high"].max())
    level_low  = float(sub["low"].min())
    cur = df.iloc[-1]
    up = cur["close"] > level_high
    down = cur["close"] < level_low
    dir_out = "up" if up else "down" if down else None
    valid = (dir_out is not None) and (direction in ("auto", dir_out))
    return {
        "pattern": "breakout",
        "is_valid": bool(valid),
        "confidence": 0.7 if valid else 0.0,
        "ref_index": -1,
        "meta": {"lookback": lookback, "level": level_high if up else level_low if down else None, "direction": dir_out, "retest": None},
    }
