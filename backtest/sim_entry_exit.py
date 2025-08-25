#!/usr/bin/env python3
"""
Simulation: Entry/Exit Signal Generator (Latest Only)
อ่าน summary CSV (จาก sim_longitudinal.py) แล้วแสดงเฉพาะสัญญาณล่าสุด
"""

import pandas as pd
import sys, os

TP_PCTS = [0.03, 0.05, 0.07]   # +3%, +5%, +7%
SL_PCT = -0.03                  # -3%

def generate_latest_signal(csv_path: str, price_col: str = None):
    df = pd.read_csv(csv_path)
    if df.empty:
        return "❌ No events found in CSV."

    row = df.iloc[-1]  # เลือกเหตุการณ์ล่าสุด
    ts = row['timestamp']
    new_pattern = row['new_pattern']
    new_stage = row['new_stage']

    # Mock entry = ใช้ราคา default (ปรับภายหลังให้ดึงจาก OHLCV ได้)
    entry_price = 100000.0

    tps = [round(entry_price*(1+p),2) for p in TP_PCTS]
    sl  = round(entry_price*(1+SL_PCT),2)

    msg = (
        f"[{ts}] Pattern: {new_pattern} ({new_stage})\n"
        f"✅ Entry: {entry_price}\n"
        f"🎯 TP: {tps[0]} / {tps[1]} / {tps[2]}\n"
        f"❌ SL: {sl}"
    )
    return msg

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backtest/sim_entry_exit.py <events_summary.csv>")
        sys.exit(1)
    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        sys.exit(f"CSV not found: {csv_path}")

    print("="*40)
    print(generate_latest_signal(csv_path))
