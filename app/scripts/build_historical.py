import os
import pandas as pd
import yfinance as yf

OUT_PATH = "app/data/historical.xlsx"
SYMBOL = "BTC-USD"
SHEETS = {
    "BTCUSDT_1D": {"interval": "1d", "start": "2010-01-01"},
    "BTCUSDT_1H": {"interval": "1h", "start": "2017-01-01"},
}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

def _download(symbol: str, start: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(symbol, start=start, interval=interval, progress=False)
        if not df.empty:
            return df
    except Exception:
        pass
    years = list(range(int(start[:4]), pd.Timestamp.utcnow().year + 1))
    parts = []
    for y in years:
        s, e = f"{y}-01-01", f"{y}-12-31"
        try:
            part = yf.download(symbol, start=s, end=e, interval=interval, progress=False)
            if not part.empty:
                parts.append(part)
        except Exception:
            continue
    return pd.concat(parts).sort_index() if parts else pd.DataFrame()

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    out = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})[
        ["open","high","low","close","volume"]
    ].copy()
    out.insert(0, "timestamp", pd.to_datetime(idx))
    out = out.dropna(subset=["timestamp","open","high","low","close","volume"])
    out = out[(out["low"]<=out["open"])&(out["low"]<=out["close"])&(out["high"]>=out["open"])&(out["high"]>=out["close"])&(out["volume"]>=0)]
    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    return out

def _resample_ohlcv(df_1h: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df_1h.empty:
        return df_1h
    x = df_1h.set_index(pd.DatetimeIndex(df_1h["timestamp"], tz="UTC"))
    o = x["open"].resample(rule).first()
    h = x["high"].resample(rule).max()
    l = x["low"].resample(rule).min()
    c = x["close"].resample(rule).last()
    v = x["volume"].resample(rule).sum()
    z = pd.concat([o,h,l,c,v], axis=1).dropna().reset_index().rename(columns={"index":"timestamp"})
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True)
    return z[["timestamp","open","high","low","close","volume"]]

def build_excel():
    print(f"Saving to: {OUT_PATH}")
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        # 1D
        raw_1d = _download(SYMBOL, SHEETS["BTCUSDT_1D"]["start"], SHEETS["BTCUSDT_1D"]["interval"])
        df_1d  = _normalize(raw_1d)
        if not df_1d.empty:
            df_1d.to_excel(writer, sheet_name="BTCUSDT_1D", index=False)
            print(f"✅ BTCUSDT_1D rows={len(df_1d)}")
        else:
            print("⚠️ BTCUSDT_1D: no data")

        # 1H
        raw_1h = _download(SYMBOL, SHEETS["BTCUSDT_1H"]["start"], SHEETS["BTCUSDT_1H"]["interval"])
        df_1h  = _normalize(raw_1h)
        if not df_1h.empty:
            df_1h.to_excel(writer, sheet_name="BTCUSDT_1H", index=False)
            print(f"✅ BTCUSDT_1H rows={len(df_1h)}")
            # 4H จาก 1H
            df_4h = _resample_ohlcv(df_1h, "4H")
            if not df_4h.empty:
                df_4h.to_excel(writer, sheet_name="BTCUSDT_4H", index=False)
                print(f"✅ BTCUSDT_4H rows={len(df_4h)}")
            else:
                print("⚠️ BTCUSDT_4H: resample empty")
        else:
            print("⚠️ BTCUSDT_1H: no data")
    print(f"🎉 Saved -> {OUT_PATH}")

if __name__ == "__main__":
    build_excel()
