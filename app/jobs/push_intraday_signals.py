from __future__ import annotations

import argparse
from typing import Dict, Optional, List
import math
import pandas as pd

# ใช้ data loader และอินดิเคเตอร์จาก analysis/*
from app.analysis.timeframes import get_data
from app.analysis.indicators import apply_indicators

TF_LIST = ["5M", "15M", "30M"]

def _format_price(x: float) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    # เลือกทศนิยม 2 ตำแหน่งเป็นกลาง ๆ (คริปโตหลัก)
    return f"{x:,.2f}"

def compute_signal(df: pd.DataFrame) -> Optional[Dict]:
    """
    Logic แบบ conservative & ชัดเจน:
      LONG  เมื่อ Close > EMA50 > EMA200 และ RSI14 >= 55 และ ATR14% >= 0.40%
      SHORT เมื่อ Close < EMA50 < EMA200 และ RSI14 <= 45 และ ATR14% >= 0.40%
    Entry = ราคา Close ล่าสุด
    SL = 1.5 * ATR14 (ทิศทางตรงข้าม)
    TP = +3%/+5%/+7% สำหรับ LONG และ -3%/-5%/-7% สำหรับ SHORT
    """
    if df is None or len(df) < 200:
        return None

    dfi = apply_indicators(df.copy())

    close = float(dfi["close"].iloc[-1])
    ema50 = float(dfi["ema50"].iloc[-1])
    ema200 = float(dfi["ema200"].iloc[-1])
    rsi14 = float(dfi["rsi14"].iloc[-1])
    atr14 = float(dfi.get("atr14", dfi.get("atr", pd.Series([float("nan")]*len(dfi)))).iloc[-1])

    atr_pct = atr14 / close if close else float("nan")
    if not all(map(lambda v: isinstance(v, float) and not math.isnan(v), [close, ema50, ema200, rsi14, atr14])):
        return None
    if atr_pct < 0.004:  # น้อยกว่า 0.40% -> งดส่งสัญญาณ (ผันผวนต่ำ)
        return None

    long_cond  = (close > ema50 > ema200) and (rsi14 >= 55)
    short_cond = (close < ema50 < ema200) and (rsi14 <= 45)

    if not (long_cond or short_cond):
        return None

    direction = "LONG" if long_cond else "SHORT"
    entry = close
    if direction == "LONG":
        sl = entry - 1.5 * atr14
        tps = [entry * 1.03, entry * 1.05, entry * 1.07]
    else:
        sl = entry + 1.5 * atr14
        tps = [entry * 0.97, entry * 0.95, entry * 0.93]

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tps": tps,
        "rsi": rsi14,
        "ema50": ema50,
        "ema200": ema200,
        "atr": atr14,
        "atr_pct": atr_pct,
        "last_time": dfi.index[-1] if hasattr(dfi.index, "tz_localize") or hasattr(dfi.index, "tz") else str(dfi.index[-1]),
    }

def analyze_symbol(symbol: str, tfs: List[str]) -> str:
    lines = []
    for tf in tfs:
        try:
            df = get_data(symbol, tf)
            sig = compute_signal(df)
            if sig:
                line = (
                    f"[{tf}] {sig['direction']} @ {_format_price(sig['entry'])}  "
                    f"TPs: {_format_price(sig['tps'][0])}, {_format_price(sig['tps'][1])}, {_format_price(sig['tps'][2])}  "
                    f"SL: {_format_price(sig['sl'])}  | RSI14 {sig['rsi']:.1f}  "
                    f"EMA50/200 {_format_price(sig['ema50'])}/{_format_price(sig['ema200'])}  "
                    f"ATR14 {_format_price(sig['atr'])} ({sig['atr_pct']*100:.2f}%)"
                )
            else:
                line = f"[{tf}] — ไม่มีสัญญาณ (เงื่อนไขยังไม่ครบ/ผันผวนต่ำ)"
        except Exception as e:
            line = f"[{tf}] ! ERROR: {e}"
        lines.append(line)

    header = f"🔔 Intraday Signals: {symbol}\n" + "-"*48
    return header + "\n" + "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="BTCUSDT")
    ap.add_argument("--tfs", nargs="*", default=TF_LIST, help="ตัวอย่าง: --tfs 5M 15M 30M")
    args = ap.parse_args()

    msg = analyze_symbol(args.symbol, args.tfs)
    print(msg)

if __name__ == "__main__":
    main()
