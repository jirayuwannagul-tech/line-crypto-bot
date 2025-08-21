# app/analysis/dow.py
from __future__ import annotations

from dataclasses import dataclass
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
    Detect swing highs/lows using a simple fractal approach.
    Returns boolean Series: (is_swing_high, is_swing_low)
    """
    high = df["high"].values
    low = df["low"].values
    n = len(df)

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
    """Count HH and HL vs LH and LL using last N swings."""
    is_sh, is_sl = _pivots(df)
    swings = df.loc[is_sh | is_sl, ["high", "low", "close"]].copy()
    swings["type"] = np.where(df.loc[is_sh | is_sl, "high"].notna(), 
                              np.where(is_sh[is_sh | is_sl], "H", "L"), "L")
    # Keep last N swings
    swings = swings.tail(max(lookback_swings, 3))

    hh_hl = 0
    lh_ll = 0
    prev_h = None
    prev_l = None
    for idx, row in swings.iterrows():
        if row.name is None:
            continue
        if row["type"] == "H":
            if prev_h is not None:
                hh_hl += int(row["high"] > prev_h)
                lh_ll += int(row["high"] < prev_h)
            prev_h = row["high"]
        else:
            if prev_l is not None:
                hh_hl += int(row["low"] > prev_l)  # HL
                lh_ll += int(row["low"] < prev_l)  # LL
            prev_l = row["low"]
    return hh_hl, lh_ll


def _ema_trend_filter(df: pd.DataFrame) -> int:
    """+1 if price > ema200 & ema50 > ema200 ; -1 if price < ema200 & ema50 < ema200 ; else 0"""
    if not {"close", "ema50", "ema200"}.issubset(df.columns):
        return 0
    last = df.iloc[-1]
    score = 0
    if pd.notna(last["ema200"]) and pd.notna(last["ema50"]) and pd.notna(last["close"]):
        if last["close"] > last["ema200"] and last["ema50"] > last["ema200"]:
            score = 1
        elif last["close"] < last["ema200"] and last["ema50"] < last["ema200"]:
            score = -1
    return score


def _sideways_filter(df: pd.DataFrame, window: int = 20, threshold: float = 0.04) -> bool:
    """
    Detect SIDE if price range over window is small relative to price level (e.g., < 4%).
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
    Return {trend_primary, trend_secondary, confidence}
    - Primary trend via HH/HL vs LH/LL and EMA filter
    - Secondary trend from recent 10 bars momentum
    - Confidence from normalized vote (0-100)
    """
    if len(df) < 50:
        return {"trend_primary": "SIDE", "trend_secondary": "SIDE", "confidence": 30}

    # Counts of structure
    hh_hl, lh_ll = _higher_highs_lows(df, lookback_swings=8)

    # Sideways quick check
    if _sideways_filter(df, window=30, threshold=0.035):
        primary = "SIDE"
    else:
        vote = 0
        vote += 1 if hh_hl > lh_ll else -1 if lh_ll > hh_hl else 0
        vote += _ema_trend_filter(df)
        primary = "UP" if vote > 0 else "DOWN" if vote < 0 else "SIDE"

    # Secondary: short momentum (last 10 bars)
    tail = df.tail(10)
    sec_vote = np.sign(tail["close"].iloc[-1] - tail["close"].iloc[0])
    if sec_vote > 0:
        secondary = "UP"
    elif sec_vote < 0:
        secondary = "DOWN"
    else:
        secondary = "SIDE"

    # Confidence
    raw_conf = 50
    # add from structure
    raw_conf += 15 if primary != "SIDE" else -10
    raw_conf += 10 if secondary == primary and primary != "SIDE" else 0
    raw_conf += 5 if abs(hh_hl - lh_ll) >= 2 else 0

    confidence = int(max(0, min(100, raw_conf)))
    return {
        "trend_primary": primary,
        "trend_secondary": secondary,
        "confidence": confidence,
    }
