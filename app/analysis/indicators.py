# app/analysis/indicators.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd

__all__ = [
    "ema",
    "rsi",
    "macd",
    "adx",
    "stoch_kd",
    "volume_metrics",
    "apply_indicators",
]

# -----------------------------
# Core moving averages
# -----------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


# -----------------------------
# RSI (Wilder)
# -----------------------------
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()

    # Wilder smoothing
    gain = gain.shift(1).ewm(alpha=1/period, adjust=False).mean()
    loss = loss.shift(1).ewm(alpha=1/period, adjust=False).mean()

    rs = gain / (loss.replace(0, np.nan))
    out = 100 - (100 / (1 + rs))
    return out.clip(0, 100)


# -----------------------------
# MACD
# -----------------------------
def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    close = pd.to_numeric(close, errors="coerce")
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = line - sig
    return line, sig, hist


# -----------------------------
# ADX (+DI, -DI)
# -----------------------------
def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = (high - low).abs()
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder smoothing
    tr_s = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean()
    plus_dm_s = pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean()

    plus_di = 100 * (plus_dm_s / tr_s)
    minus_di = 100 * (minus_dm_s / tr_s)
    dx = ( (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) ) * 100
    adx_val = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx_val, plus_di, minus_di


# -----------------------------
# Stochastic %K / %D
# -----------------------------
def stoch_kd(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k: int = 14,
    d: int = 3,
    smooth: int = 3
) -> Tuple[pd.Series, pd.Series]:
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")

    lowest_low = low.rolling(k, min_periods=k).min()
    highest_high = high.rolling(k, min_periods=k).max()

    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    k_smooth = raw_k.rolling(smooth, min_periods=smooth).mean()
    d_line = k_smooth.rolling(d, min_periods=d).mean()

    return k_smooth.clip(0, 100), d_line.clip(0, 100)


# -----------------------------
# Volume metrics (MA & Z-Score)
# -----------------------------
def volume_metrics(volume: pd.Series, window: int = 20) -> Tuple[pd.Series, pd.Series]:
    volume = pd.to_numeric(volume, errors="coerce")
    vol_ma = volume.rolling(window, min_periods=window).mean()
    vol_std = volume.rolling(window, min_periods=window).std()
    z = (volume - vol_ma) / vol_std.replace(0, np.nan)
    return vol_ma, z


# -----------------------------
# Apply all core indicators to a DataFrame
# -----------------------------
def apply_indicators(
    df: pd.DataFrame,
    cfg: Optional[Dict] = None
) -> pd.DataFrame:
    """
    Adds indicator columns to df in-place-safe manner and returns a new DataFrame.

    Columns required: high, low, close, volume
    Added columns:
      - ema20, ema50, ema200
      - rsi14
      - macd, macd_signal, macd_hist
      - adx14, plus_di14, minus_di14
      - stoch_k, stoch_d
      - vol_ma20, vol_z20
    """
    cfg = cfg or {}
    df = df.copy()

    # EMA set
    df["ema20"] = ema(df["close"], cfg.get("ema_fast", 20))
    df["ema50"] = ema(df["close"], cfg.get("ema_mid", 50))
    df["ema200"] = ema(df["close"], cfg.get("ema_slow", 200))

    # RSI
    df["rsi14"] = rsi(df["close"], cfg.get("rsi_period", 14))

    # MACD
    m_line, m_sig, m_hist = macd(
        df["close"],
        fast=cfg.get("macd_fast", 12),
        slow=cfg.get("macd_slow", 26),
        signal=cfg.get("macd_signal", 9),
    )
    df["macd"] = m_line
    df["macd_signal"] = m_sig
    df["macd_hist"] = m_hist

    # ADX
    adx_v, pdi, mdi = adx(
        df["high"], df["low"], df["close"],
        period=cfg.get("adx_period", 14),
    )
    df["adx14"] = adx_v
    df["plus_di14"] = pdi
    df["minus_di14"] = mdi

    # Stochastic
    k_line, d_line = stoch_kd(
        df["high"], df["low"], df["close"],
        k=cfg.get("stoch_k", 14),
        d=cfg.get("stoch_d", 3),
        smooth=cfg.get("stoch_smooth", 3),
    )
    df["stoch_k"] = k_line
    df["stoch_d"] = d_line

    # Volume metrics
    vol_ma, vol_z = volume_metrics(df["volume"], window=cfg.get("vol_window", 20))
    df["vol_ma20"] = vol_ma
    df["vol_z20"] = vol_z

    return df
