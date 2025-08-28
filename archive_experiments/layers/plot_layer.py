# scripts/layers/plot_layer.py

import mplfinance as mpf
from scripts.layers.config_layer import OUT_PATH

def plot_chart(df):
    # ใช้ df ที่ slice แล้วทั้งก้อน (ไม่ใช้ tail อีก)
    title = f"BTCUSDT 1D ({df.index.min().date()} → {df.index.max().date()})"
    mpf.plot(
        df,
        type="candle",
        mav=(20, 50),
        volume=True,
        title=title,
        style="yahoo",
        savefig=OUT_PATH
    )
    print(f"✅ Chart saved to {OUT_PATH}")
