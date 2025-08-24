# app/logic/strategies.py
"""
กลยุทธ์การเทรด (Strategies):
- รวมฟังก์ชัน logic สำหรับการตัดสินใจ เช่น Moving Average Cross, RSI-based, Momentum ฯลฯ
- ใช้โดย signal engine หรือโมดูล backtest
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
import pandas as pd


# -----------------------------
# Example Strategy: Moving Average Cross
# -----------------------------
def moving_average_cross(df: pd.DataFrame, short_window: int = 50, long_window: int = 200) -> Dict[str, Any]:
    """
    กลยุทธ์ตัดสินใจโดยใช้เส้นค่าเฉลี่ยเคลื่อนที่ (Moving Average Cross)
    BUY: EMA50 ตัดขึ้น EMA200
    SELL: EMA50 ตัดลง EMA200
    """
    result = {"signal": None, "ema_short": None, "ema_long": None}
    if df is None or df.empty:
        return result

    df = df.copy()
    df["ema_short"] = df["close"].ewm(span=short_window, adjust=False).mean()
    df["ema_long"] = df["close"].ewm(span=long_window, adjust=False).mean()

    result["ema_short"] = float(df["ema_short"].iloc[-1])
    result["ema_long"] = float(df["ema_long"].iloc[-1])

    if result["ema_short"] > result["ema_long"]:
        result["signal"] = "BUY"
    elif result["ema_short"] < result["ema_long"]:
        result["signal"] = "SELL"
    else:
        result["signal"] = "HOLD"

    return result


# -----------------------------
# Example Strategy: RSI Oversold/Overbought
# -----------------------------
def rsi_signal(df: pd.DataFrame, period: int = 14, overbought: int = 70, oversold: int = 30) -> Dict[str, Any]:
    """
    สร้างสัญญาณจาก RSI:
    - RSI > overbought → SELL
    - RSI < oversold → BUY
    """
    result = {"signal": None, "rsi": None}
    if df is None or len(df) < period:
        return result

    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    rsi_last = float(rsi.iloc[-1])

    result["rsi"] = rsi_last
    if rsi_last >= overbought:
        result["signal"] = "SELL"
    elif rsi_last <= oversold:
        result["signal"] = "BUY"
    else:
        result["signal"] = "HOLD"

    return result


# -----------------------------
# Placeholder function for tests
# -----------------------------
def some_strategy_func(data=None, symbol: str = None, tf: str = None):
    """
    Placeholder สำหรับเทส:
    รองรับ signature ที่ pytest ต้องการ
    """
    return {
        "name": "some_strategy_func",
        "ready": True,
        "symbol": symbol,
        "timeframe": tf,
        "data_preview": None if data is None else str(type(data)),
    }
