# app/scripts/build_historical.py
import os
import pandas as pd
import yfinance as yf

OUT_PATH = "app/data/historical.xlsx"
SYMBOL = "BTC-USD"  # สัญลักษณ์ของ Yahoo
SHEETS = {
    "BTCUSDT_1D": {"interval": "1d", "start": "2010-01-01"},  # 1D ใช้ period='max'
    "BTCUSDT_1H": {"interval": "1h", "start": "2017-01-01"},  # 1H จำกัด ~729 วันล่าสุด
}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

def _download(symbol: str, start: str, interval: str) -> pd.DataFrame:
    """
    กติกา yfinance:
      - 1d: ใช้ period='max' เพื่อดึงยาวสุด (ย้อนหลังยาว)
      - 1h: ย้อนได้ ~729 วัน → บังคับ window ภายใน 729 วันล่าสุด และดึงเป็นชิ้น 30 วัน
    """
    if interval == "1d":
        # ดึงยาวสุด
        try:
            df = yf.download(
                symbol, period="max", interval="1d",
                progress=False, auto_adjust=False
            )
            if not df.empty:
                return df
        except Exception:
            pass
        # fallback รายปี
        years = list(range(int(start[:4]), pd.Timestamp.utcnow().year + 1))
        parts = []
        for y in years:
            s, e = f"{y}-01-01", f"{y}-12-31"
            try:
                part = yf.download(
                    symbol, start=s, end=e, interval="1d",
                    progress=False, auto_adjust=False
                )
                if not part.empty:
                    parts.append(part)
            except Exception:
                continue
        return pd.concat(parts).sort_index() if parts else pd.DataFrame()

    if interval in ("1h", "60m"):
        now = pd.Timestamp.utcnow().tz_localize("UTC")
        earliest_allowed = now - pd.Timedelta(days=729)
        start_ts = max(pd.Timestamp(start).tz_localize("UTC"), earliest_allowed)

        # ดึงเป็นช่วงละ 30 วัน (กัน response ว่าง)
        parts = []
        s = start_ts
        while s < now:
            e = min(s + pd.Timedelta(days=30), now)
            try:
                part = yf.download(
                    symbol,
                    start=s.tz_convert(None),
                    end=e.tz_convert(None),
                    interval="1h",
                    progress=False,
                    auto_adjust=False
                )
                if not part.empty:
                    parts.append(part)
            except Exception:
                pass
            s = e
        return pd.concat(parts).sort_index() if parts else pd.DataFrame()

    return pd.DataFrame()

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """ปรับคอลัมน์, ทำ timestamp(UTC), คัดกรองความสมเหตุสมผล"""
    if df.empty:
        return df

    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")

    rename_map = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    out = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})

    needed = ["open", "high", "low", "close", "volume"]
    if any(c not in out.columns for c in needed):
        return pd.DataFrame()

    out = out[needed].copy()
    out.insert(0, "timestamp", pd.to_datetime(idx))
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    out = out[
        (out["low"] <= out["open"])
        & (out["low"] <= out["close"])
        & (out["high"] >= out["open"])
        & (out["high"] >= out["close"])
        & (out["volume"] >= 0)
    ]
    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    return out

def _resample_ohlcv(df_1h: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample จาก 1H ไป TF ใหญ่ (เช่น 4H)"""
    if df_1h.empty:
        return df_1h
    x = df_1h.set_index(pd.DatetimeIndex(df_1h["timestamp"], tz="UTC"))
    o = x["open"].resample(rule).first()
    h = x["high"].resample(rule).max()
    l = x["low"].resample(rule).min()
    c = x["close"].resample(rule).last()
    v = x["volume"].resample(rule).sum()
    z = pd.concat([o, h, l, c, v], axis=1).dropna().reset_index().rename(columns={"index": "timestamp"})
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True)
    return z[["timestamp", "open", "high", "low", "close", "volume"]]

def build_excel():
    print(f"Saving to: {OUT_PATH}")
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        wrote_any = False

        # ----- 1D -----
        raw_1d = _download(SYMBOL, SHEETS["BTCUSDT_1D"]["start"], SHEETS["BTCUSDT_1D"]["interval"])
        df_1d = _normalize(raw_1d)
        if not df_1d.empty:
            df_1d.to_excel(writer, sheet_name="BTCUSDT_1D", index=False)
            wrote_any = True
            print(f"✅ BTCUSDT_1D rows={len(df_1d)}")
        else:
            print("⚠️ BTCUSDT_1D: no data")

        # ----- 1H (+ 4H) -----
        raw_1h = _download(SYMBOL, SHEETS["BTCUSDT_1H"]["start"], SHEETS["BTCUSDT_1H"]["interval"])
        df_1h = _normalize(raw_1h)
        if not df_1h.empty:
            df_1h.to_excel(writer, sheet_name="BTCUSDT_1H", index=False)
            wrote_any = True
            print(f"✅ BTCUSDT_1H rows={len(df_1h)}")

            df_4h = _resample_ohlcv(df_1h, "4H")
            if not df_4h.empty:
                df_4h.to_excel(writer, sheet_name="BTCUSDT_4H", index=False)
                wrote_any = True
                print(f"✅ BTCUSDT_4H rows={len(df_4h)}")
            else:
                print("⚠️ BTCUSDT_4H: resample empty")
        else:
            print("⚠️ BTCUSDT_1H: no data")

        if not wrote_any:
            pd.DataFrame({"msg": ["no data"]}).to_excel(writer, sheet_name="EMPTY", index=False)
            print("⚠️ No data written. Created EMPTY sheet.")

    print(f"🎉 Saved -> {OUT_PATH}")

if __name__ == "__main__":
    build_excel()
