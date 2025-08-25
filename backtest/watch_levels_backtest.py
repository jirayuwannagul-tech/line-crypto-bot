#!/usr/bin/env python3
# backtest/watch_levels_backtest.py
"""
Backtest ความแม่นยำของ 'watch levels' (Support/Resistance)
- Support = rolling Low ต่ำสุด N แท่ง (shift ออก 1 แท่ง)
- Resistance = rolling High สูงสุด N แท่ง (shift ออก 1 แท่ง)
- Buffer รองรับ: pct:x.yyy (เช่น 0.002 = 0.2%) หรือ atr:x.y (เช่น 0.2 = 0.2*ATR14)
- วัดการ "แตะระดับ" ภายในขอบเขต ±buffer ในช่วงมองไปข้างหน้า 1,3,5 แท่ง
Output:
  - CSV: backtest/results_watch_levels.csv
  - สรุปผลรวม Hit Rate, Avg Days-to-Hit ต่อระดับ/ช่วงเวลา
"""

import argparse
import math
import os
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd

# ใช้ data loader ของโปรเจกต์
from app.analysis.timeframes import get_data

# -----------------------------
# Utilities
# -----------------------------
def compute_atr14(df: pd.DataFrame) -> pd.Series:
    """คำนวณ ATR14 แบบ EMA (Wilder approximate)"""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)

    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14.0, adjust=False, min_periods=14).mean()
    return atr

def parse_horizons(s: str) -> List[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]

def parse_buffer(s: str, close: float, atr: float) -> float:
    """
    รองรับ:
      - "pct:0.002"  -> 0.2% ของราคา (0.002 * close)
      - "atr:0.2"    -> 0.2 * ATR
      - "abs:100"    -> 100 หน่วยราคา
    """
    kind, val = s.split(":")
    v = float(val)
    if kind == "pct":
        return close * v
    elif kind == "atr":
        return atr * v
    elif kind == "abs":
        return v
    else:
        raise ValueError(f"buffer ไม่รองรับรูปแบบ: {s}")

def build_watch_levels(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    สร้างคอลัมน์ support/resistance จาก rolling window
    ใช้ shift(1) เพื่อไม่ให้มองอนาคต
    """
    out = df.copy()
    out["support"] = out["low"].rolling(window=lookback, min_periods=lookback).min().shift(1)
    out["resistance"] = out["high"].rolling(window=lookback, min_periods=lookback).max().shift(1)
    return out

def hit_within_window(sub: pd.DataFrame, level: float, buffer_val: float) -> Tuple[int, float]:
    """
    ตรวจว่าภายในหน้าต่าง sub (อนาคต N แท่ง):
      ถ้า bar ช่วงใดมีช่วง [low, high] คร่อม level±buffer ถือว่า 'hit'
      คืนค่า: (hit_flag 0/1, days_to_hit ถ้าไม่โดน = NaN)
    """
    for i, row in enumerate(sub.itertuples(index=False), start=1):
        lo = float(row.low)
        hi = float(row.high)
        if (lo - buffer_val) <= level <= (hi + buffer_val):
            return 1, float(i)
    return 0, float("nan")

# -----------------------------
# Core Backtest
# -----------------------------
def run_backtest(symbol: str, tf: str, lookback: int, horizons: List[int],
                 buffer_spec: str, out_csv: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # โหลดข้อมูล
    df = get_data(symbol, tf).copy()
    # ปรับคอลัมน์มาตรฐาน
    # รองรับเคสชื่อคอลัมน์ต่างกันเล็กน้อย
    rename_map = {}
    for c in ["Open", "High", "Low", "Close"]:
        if c in df.columns:
            rename_map[c] = c.lower()
    df = df.rename(columns=rename_map)
    # บังคับคอลัมน์จำเป็น
    for c in ["open", "high", "low", "close"]:
        if c not in df.columns:
            raise ValueError(f"ไม่พบคอลัมน์ '{c}' ในข้อมูล OHLCV")

    # ATR14 สำหรับ buffer แบบ atr:
    df["atr14"] = compute_atr14(df)

    # watch levels (support/resistance)
    df = build_watch_levels(df, lookback=lookback)

    # เตรียมผลต่อแท่ง
    records = []
    for idx in range(len(df)):
        if idx == 0:
            continue
        row = df.iloc[idx]
        date = df.index[idx] if df.index.name else row.get("date", idx)
        close = float(row["close"])
        atr = float(row["atr14"]) if not math.isnan(row["atr14"]) else np.nan
        support = row["support"]
        resistance = row["resistance"]

        # ข้ามถ้ายังไม่มี level (ช่วงแรกๆ)
        if pd.isna(support) or pd.isna(resistance) or pd.isna(atr):
            continue

        # สร้าง buffer value ต่อแท่ง (ใช้ close/atr ณ แท่งนี้)
        try:
            buffer_val = parse_buffer(buffer_spec, close, atr)
        except Exception:
            buffer_val = np.nan

        future = df.iloc[idx+1 : idx+1+max(horizons)]
        row_out = {
            "date": pd.to_datetime(date),
            "close": close,
            "support": float(support),
            "resistance": float(resistance),
            "atr14": atr,
            "buffer": float(buffer_val),
        }

        for h in horizons:
            sub = df.iloc[idx+1 : idx+1+h]
            # support
            s_hit, s_days = hit_within_window(sub, float(support), float(buffer_val))
            # resistance
            r_hit, r_days = hit_within_window(sub, float(resistance), float(buffer_val))
            row_out[f"support_hit_h{h}"] = s_hit
            row_out[f"support_d2h_h{h}"] = s_days
            row_out[f"resist_hit_h{h}"] = r_hit
            row_out[f"resist_d2h_h{h}"] = r_days

        records.append(row_out)

    results = pd.DataFrame.from_records(records)
    if not results.empty:
        results.sort_values("date", inplace=True)
        # บันทึก CSV
        os.makedirs(os.path.dirname(out_csv), exist_ok=True)
        results.to_csv(out_csv, index=False)

    # สรุป
    summary_rows = []
    for lvl in ["support", "resist"]:
        for h in horizons:
            key_hit = f"{lvl}_hit_h{h}"
            key_d2h = f"{lvl}_d2h_h{h}"
            part = results[[key_hit, key_d2h]].dropna()
            total = len(part)
            hits = int(part[key_hit].sum()) if total else 0
            hit_rate = (hits / total * 100.0) if total else np.nan
            avg_d2h = float(part.loc[part[key_hit] == 1, key_d2h].mean()) if hits > 0 else np.nan
            summary_rows.append({
                "level": lvl,
                "horizon": h,
                "samples": total,
                "hits": hits,
                "hit_rate_%": round(hit_rate, 2) if not np.isnan(hit_rate) else np.nan,
                "avg_days_to_hit": round(avg_d2h, 2) if not np.isnan(avg_d2h) else np.nan
            })
    summary = pd.DataFrame(summary_rows, columns=["level","horizon","samples","hits","hit_rate_%","avg_days_to_hit"])
    return results, summary

# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Backtest watch levels accuracy (Support/Resistance)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="เช่น BTCUSDT")
    parser.add_argument("--tf", type=str, default="1D", help="เช่น 1D, 4H, 1H")
    parser.add_argument("--lookback", type=int, default=30, help="จำนวนแท่งย้อนหลังสำหรับ rolling levels (default=30)")
    parser.add_argument("--horizons", type=str, default="1,3,5", help="ช่วงอนาคตที่ตรวจแตะระดับ เช่น 1,3,5")
    parser.add_argument("--buffer", type=str, default="atr:0.2", help="รูปแบบ: pct:0.002 | atr:0.2 | abs:100")
    parser.add_argument("--out", type=str, default="backtest/results_watch_levels.csv", help="พาธไฟล์ CSV ผลลัพธ์")

    args = parser.parse_args()
    horizons = parse_horizons(args.horizons)

    results, summary = run_backtest(
        symbol=args.symbol,
        tf=args.tf,
        lookback=args.lookback,
        horizons=horizons,
        buffer_spec=args.buffer,
        out_csv=args.out
    )

    if results.empty:
        print("ไม่พบผลลัพธ์ (อาจเพราะข้อมูลน้อยเกินไปสำหรับ lookback/horizons ที่ตั้ง)")
        return

    # แสดงหัวตารางผลลัพธ์และสรุป
    print(f"✅ บันทึกผล: {args.out}")
    print("\n== ตัวอย่างผล (tail) ==")
    print(results.tail(10).to_string(index=False))

    print("\n== สรุปผลรวม (Hit Rate / Avg Days-to-Hit) ==")
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
