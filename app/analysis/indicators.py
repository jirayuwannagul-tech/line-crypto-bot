# app/analysis/indicators.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# อธิบาย:
# - รวมอินดิเคเตอร์แกนหลักที่ส่วนอื่นในระบบใช้งาน (EMA/RSI/MACD/ADX/Stoch/Volume)
# - คง "ชื่อฟังก์ชันและพารามิเตอร์" เดิมทั้งหมดเพื่อไม่ให้โค้ดเก่าพัง
# - เพิ่มความยืดหยุ่นผ่าน cfg ใน apply_indicators() ให้ปรับ period ตามโปรไฟล์ได้
# =============================================================================

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

# =============================================================================
# LAYER B) CORE MOVING AVERAGE
# -----------------------------------------------------------------------------
# หมายเหตุ: ใช้ EWM ของ pandas ตั้ง min_periods=period เพื่อลดสัญญาณหลอกช่วงต้นซีรีส์
# =============================================================================
def ema(series: pd.Series, period: int) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()

# =============================================================================
# LAYER C) RSI (Wilder's smoothing)
# -----------------------------------------------------------------------------
# ไอเดีย:
# - RSI ใช้ delta แยก gain/loss แล้วทำ Wilder smoothing (EMA alpha=1/period)
# - clip ให้อยู่ 0..100 และรักษา NaN ให้ปลอดภัย
# =============================================================================
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

# =============================================================================
# LAYER D) MACD
# -----------------------------------------------------------------------------
# คืนค่า: (macd_line, signal, histogram)
# =============================================================================
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

# =============================================================================
# LAYER E) ADX (+DI / -DI)
# -----------------------------------------------------------------------------
# แนวทาง:
# - คำนวณ TR แล้ว Wilder smoothing
# - DX = |+DI - -DI| / (+DI + -DI); ADX = EMA ของ DX
# =============================================================================
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
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx_val = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx_val, plus_di, minus_di

# =============================================================================
# LAYER F) STOCHASTIC %K / %D
# -----------------------------------------------------------------------------
# - ใช้ rolling min/max แล้วทำ smoothing ต่อ ตามสูตรมาตรฐาน
# =============================================================================
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

# =============================================================================
# LAYER G) VOLUME METRICS
# -----------------------------------------------------------------------------
# คืนค่า: (vol_ma, z_score) ใช้บอก "ความผิดปกติ" ของวอลุ่ม
# =============================================================================
def volume_metrics(volume: pd.Series, window: int = 20) -> Tuple[pd.Series, pd.Series]:
    volume = pd.to_numeric(volume, errors="coerce")
    vol_ma = volume.rolling(window, min_periods=window).mean()
    vol_std = volume.rolling(window, min_periods=window).std()
    z = (volume - vol_ma) / vol_std.replace(0, np.nan)
    return vol_ma, z

# =============================================================================
# LAYER H) BUNDLE: APPLY INDICATORS ON DATAFRAME
# -----------------------------------------------------------------------------
# อธิบาย:
# - ฟังก์ชันนี้จะ "เติมคอลัมน์อินดิเคเตอร์" ลงใน DataFrame ที่มีคอลัมน์:
#     high, low, close, volume  (และปกติจะมี open/timestamp ด้วย)
# - รองรับการจูนด้วย cfg (เช่นจากโปรไฟล์ใน YAML) โดยมีค่า default ที่ปลอดภัย
# - คืน DataFrame ใหม่ (ไม่แก้ของเดิม) เพื่อลด side-effect
# =============================================================================
def apply_indicators(
    df: pd.DataFrame,
    cfg: Optional[Dict] = None
) -> pd.DataFrame:
    """
    Adds indicator columns to df in-place-safe manner and returns a new DataFrame.

    Required columns: high, low, close, volume

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

    # --- EMA set
    ema_fast_p = int(cfg.get("ema_fast", 20))
    ema_mid_p  = int(cfg.get("ema_mid", 50))
    ema_slow_p = int(cfg.get("ema_slow", 200))
    df["ema20"]  = ema(df["close"], ema_fast_p)
    df["ema50"]  = ema(df["close"], ema_mid_p)
    df["ema200"] = ema(df["close"], ema_slow_p)

    # --- RSI
    rsi_p = int(cfg.get("rsi_period", 14))
    df["rsi14"] = rsi(df["close"], rsi_p)

    # --- MACD
    macd_fast = int(cfg.get("macd_fast", 12))
    macd_slow = int(cfg.get("macd_slow", 26))
    macd_sigp = int(cfg.get("macd_signal", 9))
    m_line, m_sig, m_hist = macd(df["close"], fast=macd_fast, slow=macd_slow, signal=macd_sigp)
    df["macd"] = m_line
    df["macd_signal"] = m_sig
    df["macd_hist"] = m_hist

    # --- ADX
    adx_p = int(cfg.get("adx_period", 14))
    adx_v, pdi, mdi = adx(df["high"], df["low"], df["close"], period=adx_p)
    df["adx14"] = adx_v
    df["plus_di14"] = pdi
    df["minus_di14"] = mdi

    # --- Stochastic
    st_k = int(cfg.get("stoch_k", 14))
    st_d = int(cfg.get("stoch_d", 3))
    st_sm = int(cfg.get("stoch_smooth", 3))
    k_line, d_line = stoch_kd(df["high"], df["low"], df["close"], k=st_k, d=st_d, smooth=st_sm)
    df["stoch_k"] = k_line
    df["stoch_d"] = d_line

    # --- Volume metrics
    vol_window = int(cfg.get("vol_window", 20))
    vol_ma, vol_z = volume_metrics(df["volume"], window=vol_window)
    df["vol_ma20"] = vol_ma
    df["vol_z20"] = vol_z

    return df
