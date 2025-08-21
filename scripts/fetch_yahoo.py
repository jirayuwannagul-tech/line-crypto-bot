import os
import math
import yfinance as yf
import pandas as pd

OUT_PATH = "app/data/historical.xlsx"
SYMBOL = "BTC-USD"  # จาก Yahoo
SHEETS = {
    "BTCUSDT_1D": {"interval": "1d", "start": "2010-01-01"},
    "BTCUSDT_4H": {"interval": "4h", "start": "2017-01-01"},  # intraday จำกัดช่วง; เริ่มปี 2017 พอใช้งาน
    "BTCUSDT_1H": {"interval": "1h", "start": "2017-01-01"},
}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
writer = pd.ExcelWriter(OUT_PATH, engine="openpyxl")

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    # รองรับทั้งคอลัมน์ Date/Datetime จาก yfinance
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
        "Date": "timestamp", "Datetime": "timestamp",
    })
    if "timestamp" not in df.columns:
        df = df.reset_index().rename(columns={"index": "timestamp"})
    # ให้เป็น UTC, ลบค่าว่าง, จัดเรียงคอลัมน์
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.assign(timestamp=ts)
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    # sanity
    df = df[(df["low"] <= df["open"]) & (df["low"] <= df["close"]) &
            (df["high"] >= df["open"]) & (df["high"] >= df["close"]) &
            (df["volume"] >= 0)]
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    return df.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]]

def _download(symbol: str, start: str, interval: str) -> pd.DataFrame:
    # สำหรับ intraday Yahoo จำกัดช่วงเวลา → ใช้ period="max" ไม่ได้เสมอ
    # yfinance จะ handle เป็นช่วงยาวให้เอง; ถ้าล้มเหลวจะลองแบ่งช่วงปีละครั้ง
    try:
        df = yf.download(symbol, start=start, interval=interval, progress=False)
        if not df.empty:
            return df
    except Exception:
        pass
    # แผนสำรอง: ดึงเป็นปีๆ
    years = list(range(int(start[:4]), pd.Timestamp.utcnow().year + 1))
    parts = []
    for y in years:
        s = f"{y}-01-01"
        e = f"{y}-12-31"
        try:
            part = yf.download(symbol, start=s, end=e, interval=interval, progress=False)
            if not part.empty:
                parts.append(part)
        except Exception:
            continue
    return pd.concat(parts).sort_index() if parts else pd.DataFrame()

for sheet, opt in SHEETS.items():
    print(f"Fetching {sheet} ({opt['interval']}) ...")
    raw = _download(SYMBOL, opt["start"], opt["interval"])
    if raw.empty:
        print(f"⚠️  {sheet}: no data downloaded; skipping sheet.")
        continue
    df = _normalize(raw)
    df.to_excel(writer, sheet_name=sheet, index=False)
    print(f"✅  {sheet}: rows={len(df)}")

writer.close()
print(f"🎉 Saved -> {OUT_PATH}")
