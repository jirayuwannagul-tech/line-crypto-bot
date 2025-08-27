#!/usr/bin/env python3
# ดึงแท่งเทียน BTCUSDT 1D (ล่าสุด 500 แท่ง) จาก Binance public API
import sys, json, datetime as dt, urllib.request

symbol = "BTCUSDT"
interval = "1d"
limit = 500
url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"

with urllib.request.urlopen(url, timeout=15) as resp:
    data = json.loads(resp.read().decode())

# รูปแบบ klines: [openTime, open, high, low, close, volume, closeTime, ...]
def ts(ms): return dt.datetime.utcfromtimestamp(ms/1000).strftime("%Y-%m-%d")

rows = [{
    "date": ts(x[0]),
    "open": float(x[1]),
    "high": float(x[2]),
    "low":  float(x[3]),
    "close":float(x[4]),
    "volume":float(x[5]),
} for x in data]

print(f"Fetched: {len(rows)} candles for {symbol} ({interval})")
print("Last 3 rows:")
for r in rows[-3:]:
    print(r)
