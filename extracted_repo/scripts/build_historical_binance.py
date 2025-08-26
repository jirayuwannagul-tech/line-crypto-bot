# scripts/build_historical_binance.py
# ดึงราคา BTCUSDT จาก Binance (Spot) → สร้าง Excel: app/data/historical.xlsx
# ชีต: BTCUSDT_1D, BTCUSDT_4H, BTCUSDT_1H
# คอลัมน์: timestamp (UTC), open, high, low, close, volume (base asset volume)

from __future__ import annotations
import os
import time
import math
import requests
import pandas as pd
from dateutil import tz
from datetime import datetime, timedelta, timezone

OUT_PATH = "app/data/historical.xlsx"
SYMBOL = "BTCUSDT"

# เลือกช่วงเวลาเริ่มต้นที่ต้องการดึงข้อมูล
# ถ้าต้องการย้อนไปไกลกว่านี้ แก้ START_AT ได้ เช่น datetime(2010, 1, 1, tzinfo=timezone.utc)
START_AT = datetime(2010, 1, 1, tzinfo=timezone.utc)
END_AT   = datetime.now(timezone.utc)

# แผนที่ interval สำหรับ Binance
INTERVALS = {
    "1D":  "1d",
    "4H":  "4h",
    "1H":  "1h",
}

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"  # Spot

def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)

def _fetch_klines(symbol: str, interval: str, start: datetime, end: datetime, limit: int = 1000) -> list:
    """
    ดึง kline ทีละหน้า (paginate) ตั้งแต่ start..end รวมทุกแท่ง
    interval ตัวอย่าง: "1d", "4h", "1h"
    """
    out = []
    start_ms = _ms(start)
    end_ms   = _ms(end)

    # ระยะเวลาโดยประมาณของ 1 แท่ง (ms) สำหรับก้าวหน้า pagination
    step_map = {
        "1m": 60_000,
        "3m": 3 * 60_000,
        "5m": 5 * 60_000,
        "15m": 15 * 60_000,
        "30m": 30 * 60_000,
        "1h": 60 * 60_000,
        "2h": 2 * 60 * 60_000,
        "4h": 4 * 60 * 60_000,
        "6h": 6 * 60 * 60_000,
        "8h": 8 * 60 * 60_000,
        "12h": 12 * 60 * 60_000,
        "1d": 24 * 60 * 60_000,
        "3d": 3 * 24 * 60 * 60_000,
        "1w": 7 * 24 * 60 * 60_000,
        "1M": 30 * 24 * 60 * 60_000,
    }
    step_ms = step_map[interval] * (limit - 1)  # ก้าวทีละ ~ limit-1 แท่ง เพื่อซ้อนทับน้อย

    current = start_ms
    session = requests.Session()

    while current < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current,
            "endTime": min(current + step_ms, end_ms),
            "limit": limit,
        }

        for attempt in range(5):
            try:
                resp = session.get(BINANCE_KLINES_URL, params=params, timeout=20)
                if resp.status_code == 429:
                    # rate limit → รอสักหน่อย
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(1.5 * (attempt + 1))

        if not data:
            # ขยับหน้าต่างเวลาไปข้างหน้า
            current = params["endTime"] + step_map[interval]
            continue

        out.extend(data)

        # เลื่อน current ไปหลังแท่งสุดท้ายที่ได้ + 1ms เพื่อกันซ้ำ
        last_open_time = data[-1][0]
        current = last_open_time + step_map[interval]

        # ป้องกันลูปแรงเกิน
        time.sleep(0.05)

    return out

def _to_df(klines: list) -> pd.DataFrame:
    """
    แปลง klines (list) เป็น DataFrame ในรูปแบบที่เราต้องการ
    ตามสเปค Binance:
    0 open time (ms)
    1 open
    2 high
    3 low
    4 close
    5 volume (base asset volume)  <-- ใช้ค่านี้เป็น volume
    6 close time (ms)
    7 quote asset volume
    8 number of trades
    9 taker buy base asset volume
    10 taker buy quote asset volume
    11 ignore
    """
    if not klines:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])

    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"
    ])
    # แปลงชนิดข้อมูล
    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # timestamp ใช้ open_time และตีความเป็น UTC
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    # เลือกคอลัมน์ที่ต้องการ
    df = df[["timestamp","open","high","low","close","volume"]].sort_values("timestamp").reset_index(drop=True)

    # ตรวจความถูกต้องเบื้องต้น
    assert (df["low"] <= df[["open","close"]].min(axis=1)).all(), "พบแถวที่ low > open/close"
    assert (df["high"] >= df[["open","close"]].max(axis=1)).all(), "พบแถวที่ high < open/close"
    assert (df["volume"] >= 0).all(), "พบ volume ติดลบ"

    return df

def fetch_interval(interval_label: str) -> pd.DataFrame:
    interval = INTERVALS[interval_label]
    klines = _fetch_klines(SYMBOL, interval, START_AT, END_AT, limit=1000)
    df = _to_df(klines)
    return df

def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    print("Downloading BTCUSDT 1D ...")
    df_1d = fetch_interval("1D")
    print(f"→ {len(df_1d)} rows")

    print("Downloading BTCUSDT 4H ...")
    df_4h = fetch_interval("4H")
    print(f"→ {len(df_4h)} rows")

    print("Downloading BTCUSDT 1H ...")
    df_1h = fetch_interval("1H")
    print(f"→ {len(df_1h)} rows")

    # แปลง timestamp เป็นสตริง UTC รูปแบบเดียวกับที่ระบบคุณใช้
    for df in (df_1d, df_4h, df_1h):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")

    # เขียนเป็น Excel (3 ชีต)
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl", mode="w") as xw:
        df_1d.to_excel(xw, sheet_name="BTCUSDT_1D", index=False)
        df_4h.to_excel(xw, sheet_name="BTCUSDT_4H", index=False)
        df_1h.to_excel(xw, sheet_name="BTCUSDT_1H", index=False)

    print(f"Saved → {OUT_PATH}")

if __name__ == "__main__":
    main()
