# scripts/plot_chart.py

import sys, os
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

# ให้ Python มองเห็นโฟลเดอร์ app/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.timeframes import get_data

# โหลดข้อมูล BTCUSDT 1D
df = get_data("BTCUSDT", "1D")

# แปลง timestamp ให้เป็น datetime index
df["timestamp"] = pd.to_datetime(df["timestamp"])
df.set_index("timestamp", inplace=True)

# จัด columns ให้ตรงตามรูปแบบที่ mplfinance ต้องการ
df = df[["open", "high", "low", "close", "volume"]]

# path สำหรับ save รูป
out_path = os.path.join("app", "reports", "charts", "btcusdt_1d.png")

# Plot กราฟแท่งเทียน + EMA20 + EMA50
mpf.plot(
    df.tail(100),  # แสดง 100 แท่งล่าสุด
    type="candle",
    mav=(20, 50),
    volume=True,
    title="BTCUSDT 1D - Candlestick with EMA20 & EMA50",
    style="yahoo",
    savefig=out_path
)

print(f"✅ Chart saved to {out_path}")
