# app/analysis/dow.py
from __future__ import annotations

from typing import Dict, Literal, Tuple
import pandas as pd
import numpy as np

Trend = Literal["UP", "DOWN", "SIDE"]

__all__ = ["analyze_dow"]

# -----------------------------
# Utility: swing highs/lows via fractals
# -----------------------------
def _pivots(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    """
    Detect swing highs/lows using simple fractal approach.
    Returns: (is_swing_high, is_swing_low) as boolean Series
    """
    n = len(df)
    if n == 0:
        return pd.Series(dtype=bool), pd.Series(dtype=bool)

    high = df["high"].values
    low = df["low"].values
    swing_high = np.full(n, False)
    swing_low = np.full(n, False)

    for i in range(left, n - right):
        if high[i] == max(high[i-left:i+right+1]):
            if (high[i] > max(high[i-left:i])) and (high[i] >= max(high[i+1:i+right+1])):
                swing_high[i] = True
        if low[i] == min(low[i-left:i+right+1]):
            if (low[i] < min(low[i-left:i])) and (low[i] <= min(low[i+1:i+right+1])):
                swing_low[i] = True

    return pd.Series(swing_high, index=df.index), pd.Series(swing_low, index=df.index)

def _higher_highs_lows(df: pd.DataFrame, lookback_swings: int = 5) -> Tuple[int, int]:
    """Count HH/HL vs LH/LL in last N swings."""
    if len(df) < 3:
        return 0, 0
    is_sh, is_sl = _pivots(df)
    swings = df.loc[is_sh | is_sl, ["high", "low"]].copy()
    swings["type"] = np.where(is_sh[is_sh | is_sl], "H", "L")
    swings = swings.tail(max(lookback_swings, 3))

    hh_hl = 0
    lh_ll = 0
    prev_h, prev_l = None, None
    for _, row in swings.iterrows():
        if row["type"] == "H":
            if prev_h is not None:
                hh_hl += int(row["high"] > prev_h)
                lh_ll += int(row["high"] < prev_h)
            prev_h = row["high"]
        else:
            if prev_l is not None:
                hh_hl += int(row["low"] > prev_l)
                lh_ll += int(row["low"] < prev_l)
            prev_l = row["low"]
    return hh_hl, lh_ll

def _ema_trend_filter(df: pd.DataFrame) -> int:
    """
    Return +1 if bullish EMA alignment, -1 if bearish, else 0.
    """
    if not {"close", "ema50", "ema200"}.issubset(df.columns) or len(df) == 0:
        return 0
    last = df.iloc[-1]
    if pd.notna(last["ema200"]) and pd.notna(last["ema50"]) and pd.notna(last["close"]):
        if last["close"] > last["ema200"] and last["ema50"] > last["ema200"]:
            return 1
        elif last["close"] < last["ema200"] and last["ema50"] < last["ema200"]:
            return -1
    return 0

def _sideways_filter(df: pd.DataFrame, window: int = 20, threshold: float = 0.04) -> bool:
    """
    Detect SIDE if price range over window < threshold (relative).
    """
    sub = df.tail(window)
    if len(sub) < 5:
        return False
    rng = sub["high"].max() - sub["low"].min()
    mid = sub["close"].iloc[-1]
    if pd.isna(rng) or pd.isna(mid) or mid == 0:
        return False
    return (rng / mid) < threshold

# -----------------------------
# Public API
# -----------------------------
def analyze_dow(df: pd.DataFrame) -> Dict[str, object]:
    """
    Dow Theory Trend Analyzer.
    Returns dict {trend_primary, trend_secondary, confidence}
    """
    if len(df) < 50:
        return {"trend_primary": "SIDE", "trend_secondary": "SIDE", "confidence": 30}

    hh_hl, lh_ll = _higher_highs_lows(df, lookback_swings=8)

    if _sideways_filter(df, window=30, threshold=0.035):
        primary = "SIDE"
    else:
        vote = 0
        vote += 1 if hh_hl > lh_ll else -1 if lh_ll > hh_hl else 0
        vote += _ema_trend_filter(df)
        primary = "UP" if vote > 0 else "DOWN" if vote < 0 else "SIDE"

    # Secondary momentum (last 10 bars)
    tail = df.tail(10)
    sec_vote = np.sign(tail["close"].iloc[-1] - tail["close"].iloc[0])
    secondary = "UP" if sec_vote > 0 else "DOWN" if sec_vote < 0 else "SIDE"

    # Confidence
    raw_conf = 50
    raw_conf += 15 if primary != "SIDE" else -10
    raw_conf += 10 if secondary == primary and primary != "SIDE" else 0
    raw_conf += 5 if abs(hh_hl - lh_ll) >= 2 else 0

    confidence = int(max(0, min(100, raw_conf)))
    return {
        "trend_primary": primary,
        "trend_secondary": secondary,
        "confidence": confidence,
    }
