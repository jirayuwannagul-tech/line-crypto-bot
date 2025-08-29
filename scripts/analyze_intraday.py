from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

SYMBOL = "BTCUSDT"
TFS = ["5M","15M","30M"]  # ปรับเพิ่มได้
DATA = lambda tf: f"data/{SYMBOL}_{tf}.csv"
OUT_FILE = Path("exports/intraday_summary.txt")

def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def analyze_tf(path: str, tf: str) -> str:
    df = pd.read_csv(path, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if len(df) < 210:
        return f"[{tf}] ข้อมูลไม่พอ ({len(df)} rows) — ต้องมี > 210"

    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    # EMA
    df["ema20"]  = ema(c, 20)
    df["ema50"]  = ema(c, 50)
    df["ema200"] = ema(c, 200)

    # RSI14 (แบบ simple rolling)
    delta = c.diff()
    gain  = np.where(delta > 0, delta, 0.0)
    loss  = np.where(delta < 0, -delta, 0.0)
    roll_up   = pd.Series(gain).rolling(14).mean()
    roll_down = pd.Series(loss).rolling(14).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    df["rsi14"] = 100 - (100 / (1 + rs))

    # ATR14 (%)
    tr1 = (h - l)
    tr2 = (h - c.shift()).abs()
    tr3 = (l - c.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr14"] / c

    # recent levels
    lookback = 50
    recent_high = float(h.tail(lookback).max())
    recent_low  = float(l.tail(lookback).min())

    last = df.iloc[-1]
    ts    = last["timestamp"]
    price = float(last["close"])
    ema20, ema50, ema200 = float(last["ema20"]), float(last["ema50"]), float(last["ema200"])
    rsi14 = float(last["rsi14"])
    atrp  = float(last["atr_pct"])

    bias = "BULL" if ema50 > ema200 else "BEAR" if ema50 < ema200 else "NEUTRAL"

    long_ok  = (price > recent_high) and (ema50 > ema200) and (rsi14 >= 55)
    short_ok = (price < recent_low)  and (ema50 < ema200) and (rsi14 <= 45)

    def levels(entry, side):
        tps = [0.03, 0.05, 0.07]; slp = 0.03
        if side == "LONG":
            tp = [entry*(1+p) for p in tps]; sl = entry*(1 - slp)
        else:
            tp = [entry*(1-p) for p in tps]; sl = entry*(1 + slp)
        return tp, sl

    header = f"[{tf}] {SYMBOL} @ {price:,.2f}  Bias={bias}  RSI={rsi14:.1f}  ATR%={atrp*100:.2f}%  RH={recent_high:,.2f} RL={recent_low:,.2f}"
    if long_ok:
        tp, sl = levels(price, "LONG")
        sig = f"🚀 LONG | SL {sl:,.2f} | TP {tp[0]:,.2f}/{tp[1]:,.2f}/{tp[2]:,.2f}"
    elif short_ok:
        tp, sl = levels(price, "SHORT")
        sig = f"🧊 SHORT | SL {sl:,.2f} | TP {tp[0]:,.2f}/{tp[1]:,.2f}/{tp[2]:,.2f}"
    else:
        sig = "⏸ WAIT | เงื่อนไขยังไม่ครบ (รอ breakout/breakdown)"

    return f"{header}\n{sig}"

def main():
    Path("exports").mkdir(parents=True, exist_ok=True)
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"== INTRADAY SUMMARY ({now}) ==")

    for tf in TFS:
        p = DATA(tf)
        try:
            lines.append(analyze_tf(p, tf))
        except FileNotFoundError:
            lines.append(f"[{tf}] ไม่พบไฟล์ {p} — โปรดดึงด้วย scripts/fetch_ohlcv.py ก่อน")
        except Exception as e:
            lines.append(f"[{tf}] ERROR: {e}")

    text = "\n".join(lines)
    print(text)
    OUT_FILE.write_text(text, encoding="utf-8")
    print(f"\nSaved -> {OUT_FILE}")

if __name__ == "__main__":
    main()
