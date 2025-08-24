# scripts/layers/data_layer.py

import sys, os
import pandas as pd

# ให้ Python มองเห็นโฟลเดอร์ app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.analysis.timeframes import get_data
from scripts.layers.config_layer import SYMBOL, TIMEFRAME, START_DATE, END_DATE

def load_data():
    # โหลดข้อมูลจาก timeframes
    df = get_data(SYMBOL, TIMEFRAME)

    # จัดการ timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)

    # จัด columns ให้ตรงตามรูปแบบที่ mplfinance ต้องการ
    df = df[["open", "high", "low", "close", "volume"]]

    # slice ข้อมูลตามช่วงวันที่ที่กำหนด
    df_range = df.loc[START_DATE:END_DATE]
    return df_range


    return df_range
    