import os
import pandas as pd
import yfinance as yf

OUT_PATH = "app/data/historical.xlsx"
SYMBOL = "BTC-USD"  # จาก Yahoo
SHEETS = {
    "BTCUSDT_1D": {"interval": "1d", "start": "2010-01-01"},
    # 4H จะดึง 1h มาก่อนแล้ว resample เป็น 4H
    "BTCUSDT_4H": {"interval": "1h", "start": "2017-01-01"},
    "BTCUSDT_1H": {"interval": "1h", "start": "2017-01-01"},
}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

def _download(symbol: str, start: str, interval: str) -> pd.DataFrame:
    """
    ดึงข้อมูลจาก Yahoo Finance ด้วย yfinance
    - ใช้ง่ายสุด: ลองดึงตรง ๆ ก่อน
    - ถ้าไม่ได้ ให้ลองแบ่งช่วงเป็นปี ๆ (กันกรณีอินทราเดย์จำกัดช่วง)
    """
    try:
        df = yf.download(symbol, start=start, interval=interval, progress=False)
        if not df.empty:
            return df
    except Exception:
        pass

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

def _normalize_from_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    แปลง DataFrame จาก yfinance ให้เป็นคอลัมน์มาตรฐาน:
    timestamp (UTC), open, high, low, close, volume
    """
    if df.empty:
        return df

    # ทำให้ index เป็น UTC เสมอ
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")

    out = df.rename(
        columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )[["open", "high", "low", "close", "volume"]].copy()

    out.insert(0, "timestamp", pd.to_datetime(idx))
    # ล้าง NaN ที่จำเป็น
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    # sanity check
    out = out[
        (out["low"] <= out["open"]) &
        (out["low"] <= out["close"]) &
        (out["high"] >= out["open"]) &
        (out["high"] >= out["close"]) &
        (out["volume"] >= 0)
    ]
    # เรียงเวลา + ไม่ซ้ำ
    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    return out

def _resample_ohlcv(df_1h: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    resample OHLCV จากความถี่เล็ก → ใหญ่ (เช่น 1H → 4H)
    ใช้ timestamp เป็น DatetimeIndex ก่อน แล้วค่อย aggregate แบบ OHLCV มาตรฐาน
    """
    if df_1h.empty:
        return df_1h

    x = df_1h.copy()
    x = x.set_index(pd.DatetimeIndex(x["timestamp"], tz="UTC"))
    o = x["open"].resample(rule).first()
    h = x["high"].resample(rule).max()
    l = x["low"].resample(rule).min()
    c = x["close"].resample(rule).last()
    v = x["volume"].resample(rule).sum()

    z = pd.concat([o, h, l, c, v], axis=1).dropna()
    z = z.reset_index().rename(columns={"index": "timestamp"})
    # จัดรูปให้เหมือนเดิม
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True)
    return z.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]]

def build_excel():
    print(f"Saving to: {OUT_PATH}")
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        # 1D
        cfg = SHEETS["BTCUSDT_1D"]
        raw_1d = _download(SYMBOL, cfg["start"], cfg["interval"])
        df_1d = _normalize_from_index(raw_1d)
        if df_1d.empty:
            print("⚠️  BTCUSDT_1D: no data")
        else:
            df_1d.to_excel(writer, sheet_name="BTCUSDT_1D", index=False)
            print(f"✅  BTCUSDT_1D rows={len(df_1d)}")

        # 1H (ฐานสำหรับ 4H)
        cfg = SHEETS["BTCUSDT_1H"]
        raw_1h = _download(SYMBOL, cfg["start"], cfg["interval"])
        df_1h = _normalize_from_index(raw_1h)
        if df_1h.empty:
            print("⚠️  BTCUSDT_1H: no data")
        else:
            df_1h.to_excel(writer, sheet_name="BTCUSDT_1H", index=False)
            print(f"✅  BTCUSDT_1H rows={len(df_1h)}")

        # 4H (resample จาก 1H)
        if not df_1h.empty:
            df_4h = _resample_ohlcv(df_1h, "4H")
            if df_4h.empty:
                print("⚠️  BTCUSDT_4H: resample empty")
            else:
                df_4h.to_excel(writer, sheet_name="BTCUSDT_4H", index=False)
                print(f"✅  BTCUSDT_4H rows={len(df_4h)}")

    print(f"🎉 Saved -> {OUT_PATH}")

if __name__ == "__main__":
    build_excel()
