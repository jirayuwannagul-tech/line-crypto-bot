from __future__ import annotations
import pandas as pd
import numpy as np
from typing import List, Dict

def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(window, min_periods=1).mean()

def detect_zigzag_dynamic(
    df: pd.DataFrame,
    base_pct: float = 0.006,   # เกณฑ์พื้นฐาน 0.6%
    k: float = 1.8,            # คูณ ATR/price เพื่อปรับ threshold
    vol_window: int = 14,
    min_bars: int = 3,
    max_bars: int = 180,       # บังคับตัดถ้าแท่งยาวเกิน
    price_col: str = "close"
) -> List[Dict]:
    """
    คืนค่า segments [{'start_ts','start_px','end_ts','end_px','dir','bars'}, ...]
    ใช้ high/low เป็น extreme และ threshold = max(base_pct, k*ATR/price)
    """
    need = {"timestamp","open","high","low","close"}
    assert need.issubset(df.columns), f"columns not enough, need {need}"
    if df.empty:
        return []

    df = df.sort_values("timestamp").reset_index(drop=True).copy()
    typ = (df["high"] + df["low"] + df["close"]) / 3.0
    atr = _atr(df, vol_window)
    thr = np.maximum(base_pct, (k * (atr / typ.clip(lower=1e-9))).fillna(base_pct))

    ts = df["timestamp"].tolist()
    hi = df["high"].astype(float).tolist()
    lo = df["low"].astype(float).tolist()
    px = df[price_col].astype(float).tolist()

    segments: List[Dict] = []
    last_pivot_i = 0
    direction = None  # 'UP' หรือ 'DOWN'

    # หา direction เริ่มต้นเมื่อราคาขยับเกิน threshold
    for j in range(1, len(px)):
        chg = (px[j] - px[last_pivot_i]) / max(px[last_pivot_i], 1e-9)
        if abs(chg) >= thr[j]:
            direction = 'UP' if chg > 0 else 'DOWN'
            break
    if direction is None:
        return []

    # กำหนด extreme เริ่มต้นจาก pivot แรก
    extreme_i = last_pivot_i
    extreme_px = hi[extreme_i] if direction == 'UP' else lo[extreme_i]

    for i in range(j, len(px)):
        # อัปเดต extreme ตามทิศ
        if direction == 'UP':
            if hi[i] > extreme_px:
                extreme_px = hi[i]
                extreme_i = i
            # เงื่อนไขกลับทิศ: ย่อลงจากยอดเกิน threshold หรือยาวเกิน max_bars
            rev = (px[i] - extreme_px) / max(extreme_px, 1e-9)
            if (rev <= -thr[i] and (i - last_pivot_i) >= min_bars) or ((i - last_pivot_i) >= max_bars):
                segments.append({
                    "start_ts": ts[last_pivot_i],
                    "start_px": px[last_pivot_i],
                    "end_ts": ts[extreme_i],
                    "end_px": extreme_px,
                    "dir": "UP",
                    "bars": extreme_i - last_pivot_i
                })
                last_pivot_i = extreme_i
                direction = 'DOWN'
                extreme_i = i
                extreme_px = lo[i]
        else:  # DOWN
            if lo[i] < extreme_px:
                extreme_px = lo[i]
                extreme_i = i
            rev = (px[i] - extreme_px) / max(extreme_px, 1e-9)
            if (rev >= thr[i] and (i - last_pivot_i) >= min_bars) or ((i - last_pivot_i) >= max_bars):
                segments.append({
                    "start_ts": ts[last_pivot_i],
                    "start_px": px[last_pivot_i],
                    "end_ts": ts[extreme_i],
                    "end_px": extreme_px,
                    "dir": "DOWN",
                    "bars": extreme_i - last_pivot_i
                })
                last_pivot_i = extreme_i
                direction = 'UP'
                extreme_i = i
                extreme_px = hi[i]

    # ปิดคลื่นสุดท้ายถ้าระยะพอ
    if (extreme_i - last_pivot_i) >= min_bars:
        segments.append({
            "start_ts": ts[last_pivot_i],
            "start_px": px[last_pivot_i],
            "end_ts": ts[extreme_i],
            "end_px": extreme_px,
            "dir": direction if direction else "UP",
            "bars": extreme_i - last_pivot_i
        })

    return segments

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/mtf/BTCUSDT_1D_overlap.csv"
    df = pd.read_csv(path, parse_dates=["timestamp"])
    segs = detect_zigzag_dynamic(df, base_pct=0.006, k=1.8, vol_window=14, min_bars=3, max_bars=240)
    print(f"segments: {len(segs)}  from={df['timestamp'].min()} to={df['timestamp'].max()}")
    for s in segs[:10]:
        print(s)
