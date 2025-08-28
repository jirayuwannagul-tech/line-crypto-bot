#!/usr/bin/env python3
import os, time, sys
from datetime import datetime, timedelta, timezone
import argparse
import ccxt
import pandas as pd

# ----------------------------
# แปลงรูปแบบ TF ที่ผู้ใช้กรอก -> รูปแบบ ccxt/binance
# ----------------------------
_BINANCE_INTERVAL = {
    "1M": "1m",
    "5M": "5m",
    "15M": "15m",
    "30M": "30m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1w",
}

def _norm_tf(tf: str) -> str:
    tf_up = tf.strip().upper()
    if tf_up not in _BINANCE_INTERVAL:
        raise ValueError(f"Unsupported timeframe: {tf} (รองรับ: {', '.join(_BINANCE_INTERVAL.keys())})")
    return _BINANCE_INTERVAL[tf_up]

def _to_pair(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if "/" in s:
        return s
    # รองรับ BTCUSDT, BTC-USDT, BTC:USDT
    s = s.replace("-", "/").replace(":", "/")
    if "/" not in s:
        s = s[:3] + "/" + s[3:] if len(s) > 3 else s
    return s

# ----------------------------
# Helper: ระยะเวลา TF เป็นมิลลิวินาที
# ----------------------------
def tf_ms(tf_ccxt: str) -> int:
    n = int(tf_ccxt[:-1])
    unit = tf_ccxt[-1]
    if unit == "m": return n * 60 * 1000
    if unit == "h": return n * 60 * 60 * 1000
    if unit == "d": return n * 24 * 60 * 60 * 1000
    if unit == "w": return n * 7 * 24 * 60 * 60 * 1000
    raise ValueError(f"Unknown timeframe: {tf_ccxt}")

# ----------------------------
# ดึงแบบต่อเนื่องด้วย since (paginate)
# ----------------------------
def fetch_all_ohlcv(exchange, symbol: str, timeframe_ccxt: str, since_ms: int, until_ms: int, max_limit: int = 1000):
    all_rows = []
    cursor = since_ms
    step_ms = tf_ms(timeframe_ccxt)

    while True:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe_ccxt, since=cursor, limit=max_limit)
        except Exception as e:
            print(f"[{timeframe_ccxt}] fetch error at {datetime.fromtimestamp(cursor/1000, tz=timezone.utc)} -> {e}", file=sys.stderr)
            time.sleep(1.5)
            continue

        if not batch:
            break

        all_rows.extend(batch)

        last_ts = batch[-1][0]
        # ขยับ cursor ไปแท่งถัดไป
        next_cursor = last_ts + step_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor

        # หยุดถ้าเลยเป้าหมาย หรือท้ายช่วง (จำนวน < limit)
        if last_ts >= until_ms or len(batch) < max_limit:
            break

        # เคารพ rate limit
        time.sleep(max(getattr(exchange, "rateLimit", 200) / 1000.0, 0.2))

    if not all_rows:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])

    df = pd.DataFrame(all_rows, columns=["timestamp","open","high","low","close","volume"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # แปลง timestamp เป็น Asia/Bangkok แล้วถอด tz ออก (ให้เข้ากับไฟล์เดิม)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
    return df

def save_merge_csv(df: pd.DataFrame, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if os.path.exists(out_path):
        old = pd.read_csv(out_path)
        # ปกป้อง schema: ensure columns เดิมครบ
        want_cols = ["timestamp","open","high","low","close","volume"]
        for c in want_cols:
            if c not in df.columns:
                df[c] = pd.NA
        for c in want_cols:
            if c not in old.columns:
                old[c] = pd.NA
        # แปลง timestamp เป็น datetime (naive)
        old["timestamp"] = pd.to_datetime(old["timestamp"], errors="coerce")
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        merged = pd.concat([old[want_cols], df[want_cols]], ignore_index=True)
        merged = merged.dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        merged.to_csv(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

def parse_args():
    p = argparse.ArgumentParser(description="Fetch OHLCV from Binance via CCXT")
    p.add_argument("symbol", help="เช่น BTCUSDT หรือ BTC/USDT")
    p.add_argument("timeframe", help="หนึ่งค่า: 5M, 15M, 30M, 1H, 4H, 1D, 1W")
    p.add_argument("--start", help='วันเริ่ม (YYYY-MM-DD). ตัวอย่าง: "2024-01-01"', default=None)
    p.add_argument("--end", help='วันสิ้นสุด (YYYY-MM-DD). ไม่ใส่ = ตอนนี้', default=None)
    p.add_argument("--days", type=int, help="ระบุจำนวนวันย้อนหลังแทน --start/--end", default=None)
    p.add_argument("--limit", type=int, help="ccxt limit ต่อครั้ง (default=1000)", default=1000)
    return p.parse_args()

def main():
    args = parse_args()

    symbol_pair = _to_pair(args.symbol)
    tf_ccxt = _norm_tf(args.timeframe)
    max_limit = int(args.limit or 1000)

    # เปิด rate limit ในตัว
    exchange = ccxt.binance({"enableRateLimit": True})

    # สร้างช่วงเวลา
    now_ms = exchange.milliseconds()
    if args.days is not None:
        since_dt = datetime.now(timezone.utc) - timedelta(days=int(args.days))
        since_ms = int(since_dt.timestamp() * 1000)
        until_ms = now_ms
    else:
        if args.start:
            start_naive = datetime.strptime(args.start, "%Y-%m-%d")
            start_local = start_naive.replace(tzinfo=timezone(timedelta(hours=7)))  # Asia/Bangkok = UTC+7
            since_ms = int(start_local.astimezone(timezone.utc).timestamp() * 1000)
        else:
            # default: 5 ปี
            since_dt = datetime.now(timezone.utc) - timedelta(days=int(5*365.25))
            since_ms = int(since_dt.timestamp() * 1000)

        if args.end:
            end_naive = datetime.strptime(args.end, "%Y-%m-%d")
            end_local = end_naive.replace(hour=23, minute=59, second=59, tzinfo=timezone(timedelta(hours=7)))
            until_ms = int(end_local.astimezone(timezone.utc).timestamp() * 1000)
        else:
            until_ms = now_ms

    # ดึงข้อมูล
    print(f"== Fetch {symbol_pair} {tf_ccxt} ==")
    df = fetch_all_ohlcv(exchange, symbol_pair, tf_ccxt, since_ms, until_ms, max_limit=max_limit)

    # ตั้งชื่อไฟล์แบบชุดเดิม (BTCUSDT_5M.csv ฯลฯ)
    sym_noslash = args.symbol.replace("/", "").replace(":", "").replace("-", "")
    tf_key = [k for k, v in _BINANCE_INTERVAL.items() if v == tf_ccxt][0]
    out = f"data/{sym_noslash}_{tf_key}.csv"

    save_merge_csv(df, out)

    if len(df):
        print(f"✅ merged -> {out} (+{len(df)} rows fetched)  from={df['timestamp'].min()}  to={df['timestamp'].max()}")
    else:
        print(f"⚠️  no new data fetched for {tf_key}")

if __name__ == "__main__":
    main()
