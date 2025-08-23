import sys, os
import pandas as pd
import numpy as np

# ===== พารามิเตอร์หลัก ปรับได้ =====
WINDOW = 5                 # ขนาดหน้าต่างหาสวิง local extrema
FIB_ENTRY_MIN = 0.382
FIB_ENTRY_MAX = 0.618
FIB_STOP = 0.786
MAX_HOLD_BARS = 80         # จำกัดจำนวนแท่งในการตัดสินชนะ/แพ้
DATA_PATH = "app/data/historical.xlsx"
OUTPUT = "backtest/results_fib.csv"

# ให้หา app/ ได้ (เผื่อจะต่อยอดเรียกโมดูลในอนาคต)
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# ---------- Utils ----------
def _find_close_col(df: pd.DataFrame) -> str:
    for c in df.columns:
        if str(c).lower() in ["close", "closing price", "adj close"]:
            return c
    raise RuntimeError(f"❌ ไม่เจอคอลัมน์ราคาปิดในไฟล์: columns={list(df.columns)}")

def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    # พยายามหา column วันที่ชื่อ "date" หรือ "Date"
    date_col = None
    for c in df.columns:
        if str(c).lower() == "date":
            date_col = c
            break
    if date_col is not None:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).copy()
        df.set_index(date_col, inplace=True)
    else:
        df.index = pd.RangeIndex(start=0, stop=len(df))
    return df

def _local_extrema(prices: pd.Series, window: int):
    """หา swing highs/lows แบบง่ายจาก local extrema"""
    highs, lows = [], []
    n = len(prices)
    vals = prices.values
    idxs = prices.index
    for i in range(window, n - window):
        seg = vals[i - window:i + window + 1]
        mid = vals[i]
        if mid == seg.max() and seg.argmax() == window:
            highs.append(idxs[i])
        if mid == seg.min() and seg.argmin() == window:
            lows.append(idxs[i])
    return highs, lows

def _fib_ratio(price, swing_low, swing_high, direction="long"):
    """
    คำนวณสัดส่วน Fibonacci retracement ณ ราคา 'price'
    - long: ratio = (price - low) / (high - low)
    - short: ratio = (price - high) / (low - high)
    คืน r ในช่วง [0..1] ถ้านอกช่วงคืน None
    """
    if direction == "long":
        a, b = swing_low, swing_high
        if b == a: return None
        r = (price - a) / (b - a)
    else:
        a, b = swing_high, swing_low
        if b == a: return None
        r = (price - a) / (b - a)
    return r if 0.0 <= r <= 1.0 else None

# ---------- Core ----------
def run_fib_backtest():
    df = pd.read_excel(DATA_PATH)
    close_col = _find_close_col(df)
    df = _ensure_datetime_index(df)
    prices = df[close_col].astype(float)

    # หา swings แบบ local extrema
    swing_highs_idx, swing_lows_idx = _local_extrema(prices, WINDOW)

    # รวมและเรียง + บังคับสลับ H/L
    swings = sorted(
        [{"idx": i, "type": "H"} for i in swing_highs_idx] +
        [{"idx": i, "type": "L"} for i in swing_lows_idx],
        key=lambda x: df.index.get_loc(x["idx"]) if x["idx"] in df.index else x["idx"]
    )
    cleaned = []
    for s in swings:
        if not cleaned or cleaned[-1]["type"] != s["type"]:
            cleaned.append(s)

    results = []
    # เดินเป็นคู่ L->H (long) หรือ H->L (short)
    for a, b in zip(cleaned, cleaned[1:]):
        i_a, t_a = a["idx"], a["type"]
        i_b, t_b = b["idx"], b["type"]
        pos_a = df.index.get_loc(i_a) if i_a in df.index else i_a
        pos_b = df.index.get_loc(i_b) if i_b in df.index else i_b

        if t_a == "L" and t_b == "H":
            swing_low = prices.iloc[pos_a]
            swing_high = prices.iloc[pos_b]
            direction = "long"
            target_price = swing_high
        elif t_a == "H" and t_b == "L":
            swing_high = prices.iloc[pos_a]
            swing_low = prices.iloc[pos_b]
            direction = "short"
            target_price = swing_low
        else:
            continue

        # เริ่มสแกน entry ตั้งแต่หลังสวิง b
        start_scan = pos_b + 1
        if start_scan >= len(prices):
            continue

        entered = False
        entry_pos = None
        entry_idx = None
        entry_price = None
        tp_hit = False
        sl_hit = False

        # หาแท่งแรกที่ราคาเข้าโซน 0.382~0.618
        for j in range(start_scan, len(prices)):
            price = prices.iloc[j]
            r = _fib_ratio(price, swing_low, swing_high, direction)
            if r is None:
                continue
            if FIB_ENTRY_MIN <= r <= FIB_ENTRY_MAX:
                entered = True
                entry_pos = j
                entry_idx = prices.index[j]
                entry_price = price
                break

        if not entered:
            results.append({
                "setup_dir": direction,
                "swing_a_time": df.index[pos_a],
                "swing_b_time": df.index[pos_b],
                "entered": 0,
                "entry_time": None,
                "entry_price": None,
                "tp_price": target_price,
                "sl_by_ratio": FIB_STOP,
                "result": "SKIP",
                "bars_hold": 0
            })
            continue

        end_pos = min(entry_pos + MAX_HOLD_BARS, len(prices) - 1)
        k_last = entry_pos
        for k in range(entry_pos + 1, end_pos + 1):
            k_last = k
            price_k = prices.iloc[k]
            r_now = _fib_ratio(price_k, swing_low, swing_high, direction)

            if direction == "long":
                if price_k >= target_price:
                    tp_hit = True
                    break
                if (r_now is not None) and (r_now > FIB_STOP):
                    sl_hit = True
                    break
            else:  # short
                if price_k <= target_price:
                    tp_hit = True
                    break
                if (r_now is not None) and (r_now > FIB_STOP):
                    sl_hit = True
                    break

        outcome = "TP" if tp_hit else ("SL" if sl_hit else "TIMEOUT")
        results.append({
            "setup_dir": direction,
            "swing_a_time": df.index[pos_a],
            "swing_b_time": df.index[pos_b],
            "entered": 1,
            "entry_time": entry_idx,
            "entry_price": entry_price,
            "tp_price": target_price,
            "sl_by_ratio": FIB_STOP,
            "result": outcome,
            "bars_hold": (k_last - entry_pos)
        })

    out = pd.DataFrame(results)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    out.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"✅ Saved: {OUTPUT}")
    if len(out):
        print(out.tail(8))

def report():
    if not os.path.exists(OUTPUT):
        print("⚠️ ยังไม่มีไฟล์ผลลัพธ์ ให้รัน backtest ก่อน"); return
    df = pd.read_csv(OUTPUT)
    if df.empty:
        print("No trades."); return

    total_setups = len(df)
    entered = int((df["entered"] == 1).sum())
    tp = int((df["result"] == "TP").sum())
    sl = int((df["result"] == "SL").sum())
    timeout = int((df["result"] == "TIMEOUT").sum())
    hit_rate = (tp / entered * 100) if entered else 0.0

    print("\n=== 📊 Fibonacci Pullback Backtest (Analysis Only) ===")
    print(f"Total setups: {total_setups}")
    print(f"Entered: {entered}")
    print(f"TP: {tp} | SL: {sl} | TIMEOUT: {timeout}")
    print(f"Hit Rate (TP/Entered): {hit_rate:.2f}%")

    # แยกตามฝั่ง
    for side, g in df.groupby("setup_dir"):
        ent = int((g["entered"] == 1).sum())
        tp_ = int((g["result"] == "TP").sum())
        sl_ = int((g["result"] == "SL").sum())
        to_ = int((g["result"] == "TIMEOUT").sum())
        side_hit = (tp_ / ent * 100) if ent else 0.0
        print(f"\n— {side.upper()} —")
        print(f"Entered: {ent} | TP: {tp_} | SL: {sl_} | TIMEOUT: {to_}")
        print(f"Hit Rate: {side_hit:.2f}%")

if __name__ == "__main__":
    run_fib_backtest()
    report()
