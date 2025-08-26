# --- scripts/analyze_chart.py (DROP-IN REPLACE/วางทับไฟล์เดิมทั้งก้อน) ---
import pandas as pd
import numpy as np

PATH = "app/data/historical.xlsx"

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def analyze_sheet(sheet, window=30):
    df = pd.read_excel(PATH, sheet_name=sheet)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    df["EMA20"] = ema(df["close"], 20)
    df["EMA50"] = ema(df["close"], 50)
    df["EMA200"] = ema(df["close"], 200)
    df["RSI14"] = rsi(df["close"], 14)
    df["MACD"], df["Signal"], df["Hist"] = macd(df["close"])

    last = df.iloc[-1]
    prev = df.iloc[-2]

    s1 = min(last["low"], prev["low"])
    r1 = max(last["high"], prev["high"])

    sw = df.tail(window)
    swing_low = sw["low"].min()
    swing_high = sw["high"].max()
    diff = swing_high - swing_low
    fib_levels = {
        "0%": swing_high,
        "23.6%": swing_high - 0.236*diff,
        "38.2%": swing_high - 0.382*diff,
        "50%": swing_high - 0.5*diff,
        "61.8%": swing_high - 0.618*diff,
        "100%": swing_low
    }

    lines = []
    lines.append(f"=== {sheet} ===")
    lines.append(f"Last candle {last['timestamp']:%Y-%m-%d %H:%M:%S}  O:{last['open']:.2f} H:{last['high']:.2f} L:{last['low']:.2f} C:{last['close']:.2f} Vol:{last['volume']:.2f}")
    lines.append(f"EMA20={last['EMA20']:.2f}  EMA50={last['EMA50']:.2f}  EMA200={last['EMA200']:.2f}")
    lines.append(f"RSI14={last['RSI14']:.2f}")
    lines.append(f"MACD={last['MACD']:.2f}  Signal={last['Signal']:.2f}  Hist={last['Hist']:.2f}")
    lines.append(f"Support≈{s1:.2f}  Resistance≈{r1:.2f}")
    lines.append("Fib levels (30 candles swing):")
    for k, v in fib_levels.items():
        lines.append(f"  {k}: {v:.2f}")
    return "\n".join(lines)

def generate_report(sheets=("BTCUSDT_1D", "BTCUSDT_4H", "BTCUSDT_1H"), window=30):
    parts = [analyze_sheet(sh, window=window) for sh in sheets]
    return "\n\n".join(parts)

def main():
    # พิมพ์ลงหน้าจอเหมือนเดิมเพื่อไม่กระทบ workflow เก่า
    print(generate_report())

if __name__ == "__main__":
    main()
