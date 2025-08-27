# app/analysis/filters.py
# =============================================================================
# FILTERS — เงื่อนไขคัดกรองสัญญาณ (ไม่ตีความเชิงกลยุทธ์เกินจำเป็น)
# ใช้ร่วมกับ indicators.apply_indicators() ที่เติม ema50/ema200/rsi14/atr14/adx14
# =============================================================================
from __future__ import annotations
from typing import Optional, Literal
import pandas as pd
import numpy as np

Signal = Literal["LONG", "SHORT", "FLAT"]

# -----------------------------
# Core filters
# -----------------------------
def adx_filter(df: pd.DataFrame, min_adx: float = 25.0) -> bool:
    """ผ่านเมื่อค่า ADX ล่าสุด >= min_adx"""
    if "adx14" not in df.columns or len(df) == 0:
        return False
    val = float(df["adx14"].iloc[-1])
    return not np.isnan(val) and val >= float(min_adx)

def ema_regime(df: pd.DataFrame) -> Signal:
    """ดูโครงสร้างเทรนด์จาก EMA50/EMA200 ของแท่งล่าสุด"""
    if not {"ema50", "ema200"}.issubset(df.columns) or len(df) == 0:
        return "FLAT"
    e50 = float(df["ema50"].iloc[-1])
    e200 = float(df["ema200"].iloc[-1])
    if np.isnan(e50) or np.isnan(e200):
        return "FLAT"
    if e50 > e200:
        return "LONG"
    if e50 < e200:
        return "SHORT"
    return "FLAT"

def rsi_filter(df: pd.DataFrame, bull_min: float = 55.0, bear_max: float = 45.0) -> Signal:
    """ให้สัญญาณจาก RSI14 ล่าสุดตามเกณฑ์ที่กำหนด"""
    if "rsi14" not in df.columns or len(df) == 0:
        return "FLAT"
    r = float(df["rsi14"].iloc[-1])
    if np.isnan(r):
        return "FLAT"
    if r >= bull_min:
        return "LONG"
    if r <= bear_max:
        return "SHORT"
    return "FLAT"

# -----------------------------
# Combined logic (ตามสเปก)
# -----------------------------
def logic_filter_signal(df: pd.DataFrame,
                        min_adx: float = 25.0,
                        rsi_bull_min: float = 55.0,
                        rsi_bear_max: float = 45.0) -> Signal:
    """
    สรุปสัญญาณตามกฎ:
      - LONG:  ADX>min_adx และ EMA50>EMA200 และ RSI>=rsi_bull_min
      - SHORT: ADX>min_adx และ EMA50<EMA200 และ RSI<=rsi_bear_max
      - ไม่เข้าเงื่อนไข → FLAT
    """
    if len(df) == 0:
        return "FLAT"

    if not adx_filter(df, min_adx=min_adx):
        return "FLAT"

    regime = ema_regime(df)
    rsi_sig = rsi_filter(df, bull_min=rsi_bull_min, bear_max=rsi_bear_max)

    if regime == "LONG" and rsi_sig == "LONG":
        return "LONG"
    if regime == "SHORT" and rsi_sig == "SHORT":
        return "SHORT"
    return "FLAT"

# -----------------------------
# Compat helpers (ใช้กับโค้ดเดิม)
# -----------------------------
def trend_filter(series) -> bool:
    """
    เดิม strategies_momentum เรียกใช้งาน; ให้ True เมื่อมีโครงสร้างเทรนด์ (EMA50 != EMA200)
    """
    df = _series_to_df(series)
    if not {"ema50", "ema200"}.issubset(df.columns):
        return False
    e50 = float(df["ema50"].iloc[-1])
    e200 = float(df["ema200"].iloc[-1])
    return not (np.isnan(e50) or np.isnan(e200)) and (e50 != e200)

def volatility_filter(series, min_adx: float = 15.0) -> bool:
    """
    เดิม strategies_momentum เรียกใช้งาน; ให้ True เมื่อ ADX ล่าสุด >= min_adx
    """
    df = _series_to_df(series)
    if "adx14" not in df.columns or len(df) == 0:
        return False
    v = float(df["adx14"].iloc[-1])
    return not np.isnan(v) and v >= float(min_adx)

# -----------------------------
# Utils
# -----------------------------
def _series_to_df(series) -> pd.DataFrame:
    """รองรับทั้ง df ตรง ๆ หรือ series แบบโครงสร้างเดิม (candles list)"""
    if isinstance(series, pd.DataFrame):
        return series
    import pandas as pd
    df = pd.DataFrame(series.get("candles", []))
    if "ts" in df.columns:
        df = df.sort_values("ts").set_index("ts", drop=False)
    return df
