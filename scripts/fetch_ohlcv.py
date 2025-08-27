import os, time, math, sys
from datetime import datetime, timedelta, timezone
import ccxt
import pandas as pd

# ----------------------------
# ตั้งค่าเริ่มต้น
# ----------------------------
SYMBOL = "BTC/USDT"
TIMEFRAMES = ["1d", "4h", "1h"]  # ดึงครบทั้ง 3 TF
YEARS_BACK = 5                    # ย้อนหลัง ~5 ปี
MAX_LIMIT = 1000                  # ขีดจำกัดต่อครั้งของ Binance

# ----------------------------
# Helper: แปลง timeframe เป็น ms
# ----------------------------
def tf_ms(tf: str) -> int:
    n = int(tf[:-1])
    unit = tf[-1]
    if unit == "m": return n * 60 * 1000
    if unit == "h": return n * 60 * 60 * 1000
    if unit == "d": return n * 24 * 60 * 60 * 1000
    raise ValueError(f"Unknown timeframe: {tf}")

# ----------------------------
# ดึงแบบต่อเนื่องด้วย since
# ----------------------------
def fetch_all_ohlcv(exchange, symbol: str, timeframe: str, since_ms: int, until_ms: int):
    all_rows = []
    step = tf_ms(timeframe) * MAX_LIMIT  # กว้างสุดต่อครั้งเชิงทฤษฎี
    cursor = since_ms
    while True:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=MAX_LIMIT)
        except Exception as e:
            print(f"[{timeframe}] fetch error at {datetime.fromtimestamp(cursor/1000)} -> {e}", file=sys.stderr)
            time.sleep(1.5)
            continue

        if not batch:
            break

        all_rows.extend(batch)

        last_ts = batch[-1][0]
        # ถ้าขยับไม่ได้แล้ว ให้หยุด
        if last_ts <= cursor:
            break

        cursor = last_ts + tf_ms(timeframe)

        # เงื่อนไขหยุดเมื่อเกินช่วงที่ต้องการ หรือได้จำนวนน้อยกว่าลิมิต (ท้ายช่วง)
        if last_ts >= until_ms or len(batch) < MAX_LIMIT:
            break

        # เคารพ rate limit
        time.sleep(exchange.rateLimit / 1000.0)

    if not all_rows:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])

    # สร้าง DataFrame + ลบซ้ำ + เรียง
    df = pd.DataFrame(all_rows, columns=["timestamp","open","high","low","close","volume"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
    return df

def main():
    os.makedirs("data", exist_ok=True)

    exchange = ccxt.binance()
    now_ms = exchange.milliseconds()
    since_dt = datetime.now(timezone.utc) - timedelta(days=int(YEARS_BACK*365.25))
    since_ms = int(since_dt.timestamp() * 1000)
    until_ms = now_ms

    for tf in TIMEFRAMES:
        print(f"== Fetch {SYMBOL} {tf} (since ~{YEARS_BACK}y) ==")
        df = fetch_all_ohlcv(exchange, SYMBOL, tf, since_ms, until_ms)

        out = f"data/BTCUSDT_{tf.upper()}.csv"
        df.to_csv(out, index=False)
        if len(df):
            print(f"✅ saved {out} rows={len(df)}  from={df['timestamp'].min()}  to={df['timestamp'].max()}")
        else:
            print(f"⚠️  no data saved for {tf}")

if __name__ == "__main__":
    main()
