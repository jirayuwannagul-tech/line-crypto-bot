from __future__ import annotations
import pandas as pd
from typing import List, Dict, Literal

Direction = Literal["UP","DOWN"]

def _pct_change(a: float, b: float) -> float:
    if a == 0: 
        return 0.0
    return (b - a) / a

def detect_zigzag(
    df: pd.DataFrame,
    pct: float = 0.03,     # ทริกเกอร์เปลี่ยนทิศทาง 3%
    min_bars: int = 5,     # ระยะห่างขั้นต่ำระหว่างจุด
    price_col: str = "close"
) -> List[Dict]:
    """
    คืนค่าลิสต์ของ segments แต่ละคลื่น:
    [{ 'start_ts', 'start_px', 'end_ts', 'end_px', 'dir', 'bars' }, ...]
    """
    assert price_col in df.columns, f"missing column: {price_col}"
    if df.empty:
        return []

    ts = df["timestamp"].tolist()
    px = df[price_col].tolist()

    # เริ่มจากจุดแรก (กำหนดทิศทางเริ่มตามการเปลี่ยนแปลงครั้งแรกที่เกิน pct)
    i0 = 0
    last_pivot_i = 0
    last_pivot_px = px[0]
    direction: Direction | None = None
    segments: List[Dict] = []

    # หา direction แรกจากแท่งถัด ๆ ไป
    for j in range(1, len(px)):
        chg = _pct_change(last_pivot_px, px[j])
        if abs(chg) >= pct:
            direction = "UP" if chg > 0 else "DOWN"
            break
    if direction is None:
        return []  # ไม่มีการเปลี่ยนแปลงพอให้สร้างคลื่น

    # ติดตาม extreme ตามทิศทาง
    extreme_i = last_pivot_i
    extreme_px = last_pivot_px

    for k in range(j, len(px)):
        price = px[k]

        if direction == "UP":
            # ระหว่างขึ้น: อัปเดตจุดสูงสุด
            if price > extreme_px:
                extreme_px = price
                extreme_i = k
            # เงื่อนไขกลับทิศ: ลงมากกว่า pct จากยอด
            drawdown = _pct_change(extreme_px, price)
            if drawdown <= -pct and (extreme_i - last_pivot_i) >= min_bars:
                # ปิดคลื่นขึ้น
                segments.append({
                    "start_ts": ts[last_pivot_i],
                    "start_px": px[last_pivot_i],
                    "end_ts": ts[extreme_i],
                    "end_px": px[extreme_i],
                    "dir": "UP",
                    "bars": extreme_i - last_pivot_i
                })
                # ตั้ง pivot ใหม่จากจุดสูงสุด แล้วสลับทิศเป็นลง
                last_pivot_i = extreme_i
                last_pivot_px = extreme_px
                direction = "DOWN"
                extreme_i = k
                extreme_px = price
        else:  # direction == "DOWN"
            # ระหว่างลง: อัปเดตจุดต่ำสุด
            if price < extreme_px:
                extreme_px = price
                extreme_i = k
            # เงื่อนไขกลับทิศ: เด้งขึ้นมากกว่า pct จากก้น
            bounce = _pct_change(extreme_px, price)
            if bounce >= pct and (extreme_i - last_pivot_i) >= min_bars:
                # ปิดคลื่นลง
                segments.append({
                    "start_ts": ts[last_pivot_i],
                    "start_px": px[last_pivot_i],
                    "end_ts": ts[extreme_i],
                    "end_px": px[extreme_i],
                    "dir": "DOWN",
                    "bars": extreme_i - last_pivot_i
                })
                # ตั้ง pivot ใหม่จากจุดต่ำสุด แล้วสลับทิศเป็นขึ้น
                last_pivot_i = extreme_i
                last_pivot_px = extreme_px
                direction = "UP"
                extreme_i = k
                extreme_px = price

    # ปิดคลื่นสุดท้ายถ้าระยะพอ
    if (extreme_i - last_pivot_i) >= min_bars:
        segments.append({
            "start_ts": ts[last_pivot_i],
            "start_px": px[last_pivot_i],
            "end_ts": ts[extreme_i],
            "end_px": px[extreme_i],
            "dir": direction,  # ทิศปัจจุบัน
            "bars": extreme_i - last_pivot_i
        })

    return segments

if __name__ == "__main__":
    # ตัวอย่างการใช้งานแบบสั้น (ทดสอบเร็ว)
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/mtf/BTCUSDT_1D_overlap.csv"
    tf = path.split("_")[-2] if "_" in path else "1D"
    df = pd.read_csv(path, parse_dates=["timestamp"])
    segs = detect_zigzag(df, pct=0.03, min_bars=5)
    print(f"{tf} segments: {len(segs)} ตัวอย่าง 5 รายการแรก:")
    for s in segs[:5]:
        print(s)
