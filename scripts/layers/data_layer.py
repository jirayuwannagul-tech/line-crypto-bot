# scripts/layers/data_layer.py

import sys, os
import pandas as pd

# ให้ Python มองเห็นโฟลเดอร์ app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.analysis.timeframes import get_data
from scripts.layers.config_layer import SYMBOL, TIMEFRAME, START_DATE, END_DATE

def load_data(start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """โหลดและ slice ข้อมูลตามช่วงวันที่ที่กำหนด (รวม start/end)"""
    s = start_date or START_DATE
    e = end_date   or END_DATE

    df = get_data(SYMBOL, TIMEFRAME)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)

    # columns ตามรูปแบบที่ mplfinance ต้องการ
    df = df[["open", "high", "low", "close", "volume"]]

    # slice ช่วงวันที่
    df_range = df.loc[s:e]

    if df_range.empty:
        raise ValueError(f"No data in range {s} → {e}. Check dates/timeframe.")

    return df_range
