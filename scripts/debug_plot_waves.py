import os
import pandas as pd
import matplotlib.pyplot as plt

from app.analysis.data_loader import get_data
from app.analysis.elliott import _build_swings  # ใช้เฉพาะ debug

SYMBOL = "BTC/USDT"
TF = "1d"
LIMIT = 400
OUT_DIR = "out/wf"
os.makedirs(OUT_DIR, exist_ok=True)

# 1) โหลดราคา + แปลง dtype
df = get_data(SYMBOL, TF, limit=LIMIT).copy()
num_cols = ["open","high","low","close","volume","quote_asset_volume",
            "taker_buy_base_asset_volume","taker_buy_quote_asset_volume"]
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

# 2) สร้าง swing (จุด L/H)
sw = _build_swings(df)   # DataFrame คอลัมน์: idx, timestamp, price, type (L/H)

# 3) พล็อตกราฟ (ห้ามตั้งสีเองตามกฎ)
plt.figure(figsize=(12,5))
plt.plot(df["timestamp"], df["close"], label="close")
# แยก L/H
swL = sw[sw["type"]=="L"]
swH = sw[sw["type"]=="H"]
plt.scatter(swL["timestamp"], swL["price"], marker="v", label="L (swing low)")
plt.scatter(swH["timestamp"], swH["price"], marker="^", label="H (swing high)")
plt.title(f"{SYMBOL} {TF} — swings (debug)")
plt.legend()
plt.tight_layout()

out_path = os.path.join(OUT_DIR, f"waves_{SYMBOL.replace('/','_')}_{TF}.png")
plt.savefig(out_path)
print(f"[OK] saved: {out_path}")
