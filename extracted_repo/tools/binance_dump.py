#!/usr/bin/env python3
"""
ดึงแท่งราคา Spot จาก Binance (api.binance.com/api/v3/klines) แล้วเซฟเป็น CSV
คอลัมน์: timestamp, open, high, low, close, volume (UTC)

ตัวอย่างใช้งาน:
  python tools/binance_dump.py BTCUSDT 1d 2022-01-01 app/data/BTCUSDT_1D.csv
  python tools/binance_dump.py BTCUSDT 4h 2023-01-01 app/data/BTCUSDT_4H.csv
"""
import sys, time, argparse
from typing import Optional, List
import requests
import pandas as pd

BASE_URL = "https://api.binance.com/api/v3/klines"
LIMIT = 1000

def to_ms(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    return int(pd.Timestamp(date_str, tz="UTC").timestamp() * 1000)

def fetch_klines(symbol: str, interval: str, start_ms: Optional[int], end_ms: Optional[int]) -> list:
    params = {"symbol": symbol.upper(), "interval": interval, "limit": LIMIT}
    if start_ms is not None: params["startTime"] = start_ms
    if end_ms   is not None: params["endTime"]   = end_ms
    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def download(symbol: str, interval: str, start_date: str, out_csv: str,
             end_date: Optional[str] = None, sleep_sec: float = 0.2):
    start_ms = to_ms(start_date)
    end_ms   = to_ms(end_date)
    all_rows: List[list] = []
    cur = start_ms
    last_open = None
    while True:
        data = fetch_klines(symbol, interval, cur, end_ms)
        if not data: break
        all_rows.extend(data)
        last_open = data[-1][0]
        if len(data) < LIMIT: break
        if cur is not None and last_open is not None and last_open <= cur: break
        cur = last_open + 1
        time.sleep(sleep_sec)
    if not all_rows:
        print("⚠️ ไม่พบข้อมูลจาก Binance")
        pd.DataFrame(columns=["timestamp","open","high","low","close","volume"]).to_csv(out_csv, index=False)
        return
    df = pd.DataFrame(all_rows, columns=[
        "open_time","open","high","low","close","volume","close_time",
        "qav","num_trades","tbbav","tbqav","ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["timestamp","open","high","low","close","volume"]].dropna().sort_values("timestamp")
    df.to_csv(out_csv, index=False)
    print(f"✅ saved {out_csv} rows={len(df)} range={df['timestamp'].min()} → {df['timestamp'].max()}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="เช่น BTCUSDT")
    ap.add_argument("interval", help="เช่น 1d,4h,1h")
    ap.add_argument("start", help="วันที่เริ่ม เช่น 2022-01-01")
    ap.add_argument("out_csv", help="ไฟล์ปลายทาง เช่น app/data/BTCUSDT_1D.csv")
    ap.add_argument("--end", default=None, help="วันที่สิ้นสุด (ไม่ใส่ = ปัจจุบัน)")
    args = ap.parse_args()
    download(args.symbol, args.interval, args.start, args.out_csv, end_date=args.end)

if __name__ == "__main__":
    main()
