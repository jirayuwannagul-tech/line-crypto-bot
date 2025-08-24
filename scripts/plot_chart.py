# scripts/plot_chart.py

import matplotlib.pyplot as plt
import mplfinance as mpf
from app.analysis.timeframes import get_data

# โหลดข้อมูล BTCUSDT 1D
df = get_data("BTCUSDT", "1D")

# ตั้งค่า index ให้เป็น datetime
df.index = df["timestamp"]
df = df[["open", "high", "low", "close", "volume"]]

# Plot กราฟแท่งเทียน + EMA20 + EMA50
mpf.plot(
    df.tail(100),  # แสดง 100 แท่งล่าสุด
    type="candle",
    mav=(20, 50),
    volume=True,
    title="BTCUSDT 1D - Candlestick with EMA20 & EMA50",
    style="yahoo",
    savefig="app/reports/charts/btcusdt_1d.png"
)

print("✅ Chart saved to app/reports/charts/btcusdt_1d.png")
