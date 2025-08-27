# app/analysis/filters.py
# NOTE: แทนที่ทั้งไฟล์นี้
from __future__ import annotations

from typing import Union, Dict, Any, Iterable
import numpy as np
import pandas as pd


__all__ = [
    "trend_filter",
    "volatility_filter",
    "volume_filter",
    "is_sideway_df",
    "side_confidence",
]


# ----------------------------- helpers ----------------------------- #
def _series_to_df(series: Union[pd.DataFrame, Dict[str, Any], Iterable[Dict[str, Any]]]) -> pd.DataFrame:
    """
    รองรับทั้ง:
      - DataFrame ที่มีคอลัมน์ ['open','high','low','close','volume','ts'] บางคอลัมน์อาจไม่มี
      - dict ที่มี key 'candles': list[dict]
      - dict ของ "แท่งเดียว" ที่มีคีย์ open/high/low/close (และอาจมี volume, ts)
      - iterable ของ dict แทน candles โดยตรง

    จะคืน DataFrame ที่ sort ตาม 'ts' ถ้ามี
    """
    if isinstance(series, pd.DataFrame):
        df = series.copy()
    elif isinstance(series, dict):
        if "candles" in series and isinstance(series["candles"], Iterable):
            df = pd.DataFrame(series["candles"])
        else:
            # dict ของแท่งเดียว เช่น {"open":..., "high":..., "low":..., "close":..., "ts":...}
            # หรือใช้คีย์ย่อ o/h/l/c/v/t
            # แปลงเป็น DataFrame หนึ่งแถว
            df = pd.DataFrame([series])
    else:
        # สมมุติเป็น iterable ของแท่งเทียน (list[dict])
        df = pd.DataFrame(list(series))

    # มาตรฐานชื่อคอลัมน์
    cols_map = {
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "t": "ts",
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume", "Timestamp": "ts",
    }
    for k, v in cols_map.items():
        if k in df.columns and v not in df.columns:
            df[v] = df[k]

    # ให้มีคอลัมน์หลัก ถ้าไม่มีให้เดา/เติม NaN
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"missing price column: {col}")
    if "volume" not in df.columns:
        df["volume"] = np.nan
    if "ts" not in df.columns:
        # ถ้าไม่มี ts ใช้ index เป็นลำดับเวลา
        df["ts"] = np.arange(len(df), dtype="int64")

    # บังคับชนิดตัวเลข
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # sort by ts
    df = df.sort_values("ts").reset_index(drop=True)

    return df


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=max(2, span // 2)).mean()


def _slope(s: pd.Series, window: int = 5) -> float:
    """ประมาณความชันเชิงเส้น (normalized) ช่วงท้ายของ series"""
    if len(s) < max(3, window):
        return 0.0
    y = s.dropna().to_numpy()[-window:]
    x = np.arange(len(y), dtype="float64")
    # linear regression slope
    x_mean = x.mean()
    y_mean = y.mean()
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        return 0.0
    m = np.sum((x - x_mean) * (y - y_mean)) / denom
    # normalize ด้วยราคาเฉลี่ยเพื่อลด scale effect
    return float(m / max(1e-9, y_mean))


# ----------------------------- core filters ----------------------------- #
def trend_filter(
    series: Union[pd.DataFrame, Dict[str, Any], Iterable[Dict[str, Any]]],
    ema_fast: int = 20,
    ema_slow: int = 50,
    slope_window: int = 8,
    slope_eps: float = 1e-4,
) -> bool:
    """
    ให้ True เมื่อ 'มีเทรนด์' (ทั้งขาขึ้นหรือขาลง) โดยดู:
      1) EMA fast vs slow (แยก up/down)
      2) slope ของ EMA fast มีนัยยะ (เกิน slope_eps)
    """
    df = _series_to_df(series)
    close = df["close"]
    ema_f = _ema(close, ema_fast)
    ema_s = _ema(close, ema_slow)

    # เทรนด์ขึ้นหรือลง
    up_trend = (ema_f.iloc[-1] > ema_s.iloc[-1]) and (_slope(ema_f, slope_window) > slope_eps)
    down_trend = (ema_f.iloc[-1] < ema_s.iloc[-1]) and (_slope(ema_f, slope_window) < -slope_eps)

    return bool(up_trend or down_trend)


def volatility_filter(
    series: Union[pd.DataFrame, Dict[str, Any], Iterable[Dict[str, Any]]],
    min_atr_pct: float = 0.002,
    atr_window: int = 14,
) -> bool:
    """
    ให้ True เมื่อความผันผวนพอเหมาะ (ATR เฉลี่ย/ราคาเฉลี่ย >= min_atr_pct)
    ใช้เป็นตัวกันตลาดแคบมาก ๆ
    """
    df = _series_to_df(series)
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([
        (h - l),
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_window, min_periods=max(3, atr_window // 2)).mean()
    ref_price = c.rolling(atr_window, min_periods=max(3, atr_window // 2)).mean()
    atr_pct = (atr / ref_price).iloc[-1]
    if pd.isna(atr_pct):
        return False
    return bool(atr_pct >= min_atr_pct)


def volume_filter(
    series: Union[pd.DataFrame, Dict[str, Any], Iterable[Dict[str, Any]]],
    min_multiple_of_avg: float = 1.0
) -> bool:
    """
    ตรวจว่า volume ล่าสุดสูงกว่าค่าเฉลี่ย (ทั้งชุด) ตาม multiple ที่กำหนดหรือไม่
    ถ้าไม่มี volume ในข้อมูลจะคืน False
    """
    df = _series_to_df(series)
    if "volume" not in df.columns or df["volume"].isna().all():
        return False
    avg = df["volume"].mean(skipna=True)
    last = df["volume"].iloc[-1]
    if pd.isna(last) or pd.isna(avg):
        return False
    return bool(last > avg * float(min_multiple_of_avg))


def is_sideway_df(
    df: pd.DataFrame,
    threshold: float = 0.01,
    window: int = 20,
) -> pd.Series:
    """
    คืนค่าเป็น pd.Series ของ mask (True=sideway) ยาวเท่ากับ df.index
    เกณฑ์: rolling ((max-min)/mean) ของ close < threshold
    แถวที่ข้อมูลไม่พอ (ช่วงต้น) จะให้ False
    """
    if "close" not in df:
        return pd.Series([False] * len(df), index=df.index)

    c = pd.to_numeric(df["close"], errors="coerce")
    roll_max = c.rolling(window, min_periods=window).max()
    roll_min = c.rolling(window, min_periods=window).min()
    roll_mean = c.rolling(window, min_periods=window).mean().replace(0, np.nan)

    pct_range = (roll_max - roll_min) / roll_mean
    mask = (pct_range < float(threshold)).fillna(False)

    # จัด index ให้ตรงและยาวเท่ากัน
    mask = mask.reindex(index=df.index, fill_value=False)
    return mask


def side_confidence(
    series_or_df: Union[pd.DataFrame, Dict[str, Any], Iterable[Dict[str, Any]]],
    window: int = 50,
) -> float:
    """
    คืนค่า 0..1 แทนระดับความมั่นใจว่า 'sideway'
    วัดจาก rolling std ของ close เทียบกับราคาเฉลี่ยในหน้าต่าง window ล่าสุด

    - 0  = มีแนวโน้ม/ผันผวนสูง (ไม่ใช่ sideway)
    - 1  = ผันผวนต่ำมาก (น่าจะ sideway)
    """
    df = _series_to_df(series_or_df) if not isinstance(series_or_df, pd.DataFrame) else series_or_df
    c = pd.to_numeric(df["close"], errors="coerce")
    if len(c) < max(10, window):
        return 0.0
    w = int(window)
    roll_std = c.rolling(w, min_periods=w // 2).std()
    roll_mean = c.rolling(w, min_periods=w // 2).mean().replace(0, np.nan)
    vol_ratio = (roll_std / roll_mean).iloc[-1]
    if pd.isna(vol_ratio):
        return 0.0

    # map vol_ratio → confidence (ยิ่ง vol ต่ำ → confidence สูง)
    # ปกติ 0.002~0.02 สำหรับสินทรัพย์ใหญ่ใน TF สูง ๆ; clamp เพื่อความเสถียร
    lo, hi = 0.002, 0.02
    x = float((vol_ratio - lo) / (hi - lo))
    x = max(0.0, min(1.0, x))
    return float(1.0 - x)
