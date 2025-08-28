# scripts/build_historical_binance.py
# ดึงราคา BTCUSDT จาก Binance (Spot) → สร้าง Excel: app/data/historical.xlsx
# ชีต: BTCUSDT_1D, BTCUSDT_4H, BTCUSDT_1H, BTCUSDT_30M, BTCUSDT_15M, BTCUSDT_5M
# คอลัมน์: timestamp (UTC), open, high, low, close, volume (base asset volume)

from __future__ import annotations
import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone

OUT_PATH = "app/data/historical.xlsx"
SYMBOL = "BTCUSDT"

# กำหนดช่วงเวลา
START_AT = datetime(2010, 1, 1, tzinfo=timezone.utc)
END_AT   = datetime.now(timezone.utc)

# แผนที่ interval สำหรับ Binance
INTERVALS = {
    "1D":  "1d",
    "4H":  "4h",
    "1H":  "1h",
    "30M": "30m",
    "15M": "15m",
    "5M":  "5m",
}

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)

def _fetch_klines(symbol: str, interval: str, start: datetime, end: datetime, limit: int = 1000) -> list:
    out = []
    start_ms = _ms(start)
    end_ms   = _ms(end)

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
    step_ms = step_map[interval] * (limit - 1)

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
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1.5 * (attempt + 1))

        if not data:
            current = params["endTime"] + step_map[interval]
            continue

        out.extend(data)
        last_open_time = data[-1][0]
        current = last_open_time + step_map[interval]
        time.sleep(0.05)

    return out

def _to_df(klines: list) -> pd.DataFrame:
    if not klines:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])

    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"
    ])

    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df[["timestamp","open","high","low","close","volume"]].sort_values("timestamp").reset_index(drop=True)

    return df

def fetch_interval(interval_label: str) -> pd.DataFrame:
    interval = INTERVALS[interval_label]
    klines = _fetch_klines(SYMBOL, interval, START_AT, END_AT, limit=1000)
    return _to_df(klines)

def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    data_frames = {}
    for lbl in ["1D", "4H", "1H", "30M", "15M", "5M"]:
        print(f"Downloading BTCUSDT {lbl} ...")
        df = fetch_interval(lbl)
        print(f"→ {len(df)} rows")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        data_frames[lbl] = df

    with pd.ExcelWriter(OUT_PATH, engine="openpyxl", mode="w") as xw:
        for lbl, df in data_frames.items():
            df.to_excel(xw, sheet_name=f"BTCUSDT_{lbl}", index=False)

    print(f"Saved → {OUT_PATH}")

if __name__ == "__main__":
    main()
