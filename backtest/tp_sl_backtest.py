#!/usr/bin/env python3
# backtest/tp_sl_backtest.py
"""
Mini-Backtest: จากจุด Entry → แตะ TP ก่อน หรือ SL ก่อน? (2022→ปัจจุบัน)
- Entry = ราคา close ของแท่ง
- TP/SL = คิดเป็น % จากราคา entry
- ตรวจอนาคต n แท่ง (horizon) ว่าแตะ TP ก่อน หรือ SL ก่อน
- ถ้าไม่แตะในกรอบ n แท่ง → outcome = "none"
- ถ้าแท่งเดียวกันแตะได้ทั้ง TP และ SL → tie_policy (sl_first | tp_first | none)

CLI ตัวอย่าง:
python backtest/tp_sl_backtest.py --symbol BTCUSDT --tf 1D --start 2022-01-01 --tp 0.05 --sl 0.03 --horizon 5 --side long
"""

from __future__ import annotations
import argparse
from typing import Tuple
import numpy as np
import pandas as pd

# ใช้ data loader ของโปรเจกต์
from app.analysis.timeframes import get_data


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """ปรับชื่อคอลัมน์/ดัชนีให้เป็นมาตรฐาน"""
    df = df.copy()
    # ชื่อคอลัมน์เป็นตัวเล็ก
    df.columns = [str(c).lower() for c in df.columns]
    # บังคับคอลัมน์ที่ต้องมี
    for c in ("open", "high", "low", "close"):
        if c not in df.columns:
            raise ValueError(f"ไม่พบคอลัมน์ '{c}' ในข้อมูล OHLCV")
    # ทำ index ให้เป็น datetime ถ้าเป็นไปได้
    if "date" in df.columns and not np.issubdtype(df.index.dtype, np.datetime64):
        try:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        except Exception:
            pass
    if not np.issubdtype(df.index.dtype, np.datetime64):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass
    return df.sort_index()


def _levels_for_side(entry: float, tp_pct: float, sl_pct: float, side: str) -> Tuple[float, float]:
    """คำนวณระดับ TP/SL สำหรับฝั่ง long/short"""
    side = side.lower()
    if side == "long":
        tp = entry * (1 + tp_pct)
        sl = entry * (1 - sl_pct)
    elif side == "short":
        tp = entry * (1 - tp_pct)   # กำไรเมื่อราคาลงถึงระดับนี้
        sl = entry * (1 + sl_pct)   # ขาดทุนเมื่อราคาขึ้นถึงระดับนี้
    else:
        raise ValueError("side ต้องเป็น 'long' หรือ 'short'")
    return tp, sl


def _outcome_next_bars(
    future_slice: pd.DataFrame,
    tp_level: float,
    sl_level: float,
    side: str,
    tie_policy: str = "sl_first",
) -> Tuple[str, float]:
    """
    ไล่ตรวจทีละแท่งในอนาคต:
      - ถ้าทั้ง TP และ SL เกิดในแท่งเดียวกัน → ใช้ tie_policy
      - ถ้าเจออย่างใดอย่างหนึ่ง → คืน ('TP' หรือ 'SL', days_to_hit)
      - ถ้าไม่เจอเลย → ('none', nan)
    """
    side = side.lower()
    tie_policy = tie_policy.lower()
    for i, row in enumerate(future_slice.itertuples(index=False), start=1):
        lo = float(row.low)
        hi = float(row.high)
        if side == "long":
            hit_tp = hi >= tp_level
            hit_sl = lo <= sl_level
        else:  # short
            hit_tp = lo <= tp_level
            hit_sl = hi >= sl_level

        if hit_tp and hit_sl:
            if tie_policy == "sl_first":
                return "SL", float(i)
            elif tie_policy == "tp_first":
                return "TP", float(i)
            else:
                return "none", float("nan")
        if hit_sl:
            return "SL", float(i)
        if hit_tp:
            return "TP", float(i)
    return "none", float("nan")


def run_backtest(symbol: str, tf: str, start: str, end: str | None,
                 tp_pct: float, sl_pct: float, horizon: int,
                 side: str, tie_policy: str, out_csv: str) -> pd.DataFrame:
    df = get_data(symbol, tf)
    df = _normalize_ohlc(df)
    # ตัดช่วงเวลา
    if start and end:
        df = df.loc[start:end]
    elif start:
        df = df.loc[start:]
    elif end:
        df = df.loc[:end]
    if len(df) < horizon + 2:
        print(f"⚠️ ข้อมูลมีเพียง {len(df)} แท่ง ไม่พอสำหรับ horizon={horizon}")
        return pd.DataFrame()

    recs = []
    for i in range(len(df) - horizon):
        entry_ts = df.index[i]
        entry = float(df.iloc[i]["close"])
        tp_level, sl_level = _levels_for_side(entry, tp_pct, sl_pct, side)
        future = df.iloc[i+1 : i+1+horizon]
        outcome, d2h = _outcome_next_bars(future, tp_level, sl_level, side, tie_policy)
        recs.append({
            "date": pd.to_datetime(entry_ts),
            "entry": entry,
            "tp_level": tp_level,
            "sl_level": sl_level,
            "outcome": outcome,
            "days_to_hit": d2h,
            "side": side,
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "horizon": horizon,
        })
    out = pd.DataFrame.from_records(recs)
    out.to_csv(out_csv, index=False)
    return out


def main():
    p = argparse.ArgumentParser(description="Backtest: แตะ TP ก่อน หรือ SL ก่อน?")
    p.add_argument("--symbol", type=str, default="BTCUSDT")
    p.add_argument("--tf", type=str, default="1D")
    p.add_argument("--start", type=str, default="2022-01-01")
    p.add_argument("--end", type=str, default=None)
    p.add_argument("--tp", "--tp-pct", dest="tp_pct", type=float, default=0.05,
                   help="เช่น 0.05 = +5%")
    p.add_argument("--sl", "--sl-pct", dest="sl_pct", type=float, default=0.03,
                   help="เช่น 0.03 = -3%")
    p.add_argument("--horizon", type=int, default=5, help="จำนวนแท่งอนาคตที่อนุญาตให้แตะ")
    p.add_argument("--side", type=str, default="long", choices=["long", "short"])
    p.add_argument("--tie-policy", type=str, default="sl_first",
                   choices=["sl_first", "tp_first", "none"])
    p.add_argument("--out", type=str, default="backtest/results_tp_sl.csv")
    args = p.parse_args()

    df = run_backtest(
        symbol=args.symbol,
        tf=args.tf,
        start=args.start,
        end=args.end,
        tp_pct=args.tp_pct,
        sl_pct=args.sl_pct,
        horizon=args.horizon,
        side=args.side,
        tie_policy=args.tie_policy,
        out_csv=args.out,
    )

    # สรุปผล
    counts = df["outcome"].value_counts(dropna=False).to_dict()
    total = len(df)
    wins = int((df["outcome"] == "TP").sum())
    losses = int((df["outcome"] == "SL").sum())
    none = int((df["outcome"] == "none").sum())
    win_rate = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else float("nan")

    print("== Params ==")
    print(f"symbol={args.symbol} tf={args.tf} period={args.start}..{args.end or 'latest'} side={args.side}")
    print(f"tp={args.tp_pct*100:.2f}% sl={args.sl_pct*100:.2f}% horizon={args.horizon} tie={args.tie_policy}")
    print("\n== Summary ==")
    print(f"TP: {wins}  | SL: {losses}  | none: {none}  | total: {total}")
    print(f"Win rate (เฉพาะ TP/SL ที่เกิด): {win_rate:.2f}%")
    print(f"✅ saved: {args.out}")

if __name__ == "__main__":
    main()
