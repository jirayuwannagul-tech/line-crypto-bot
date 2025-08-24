# backtest/runner.py  ← ใช้ไฟล์เดิม จัดเลเยอร์ให้ชัดในไฟล์เดียว

import sys, os
import pandas as pd

# ===== Layer 0: Path =====
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # ให้ import app/ ได้
from app.analysis import dow


# ===== Layer 1: Data (โหลด + filter) =====
def load_data(path="app/data/historical.xlsx", start_date=None, end_date=None):
    df = pd.read_excel(path)

    # หาคอลัมน์ราคาปิด (ตามโค้ดเดิม)
    close_col = None
    for c in df.columns:
        if str(c).lower() in ["close", "closing price", "adj close"]:
            close_col = c
            break
    if close_col is None:
        raise RuntimeError(f"❌ ไม่เจอ column ราคาใน {path}, columns = {df.columns}")

    # ใช้ 'Date' ตามโค้ดเดิม (ไม่เปลี่ยน logic)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        if start_date and end_date:
            df = df.loc[start_date:end_date]

    return df, close_col


# ===== Layer 2: Logic (วิเคราะห์ทีละแท่ง) =====
def predict_trend_for_row(sub_df):
    """เรียกใช้ dow.detect_swings หรือ dow.analyze_dow ตามที่มีอยู่ (ตามโค้ดเดิม)"""
    try:
        swings = dow.detect_swings(sub_df)
    except AttributeError:
        swings = (dow.analyze_dow(sub_df) if hasattr(dow, "analyze_dow") else {})
    return swings.get("trend_primary", None)


# ===== Layer 3: Backtest (วน loop และประกอบผลลัพธ์) =====
def run_dow_backtest(start_date=None, end_date=None, data_path="app/data/historical.xlsx"):
    df, close_col = load_data(data_path, start_date, end_date)

    results = []
    for i in range(50, len(df)):               # คง logic เดิม
        sub_df = df.iloc[:i].copy()
        trend_pred = predict_trend_for_row(sub_df)

        # สร้าง label จริงจากแท่งถัดไป (ตามโค้ดเดิม)
        if i + 1 < len(df):
            real_trend = "UP" if df[close_col].iloc[i + 1] > df[close_col].iloc[i] else "DOWN"
        else:
            real_trend = None

        results.append({
            "date": df.index[i] if hasattr(df, "index") else i,
            "close": df[close_col].iloc[i],
            "trend_pred": trend_pred,
            "real_trend": real_trend,
            "hit": 1 if trend_pred == real_trend else 0
        })

    # ===== Layer 4: Report (บันทึก CSV + แสดงท้ายตาราง) =====
    bt = pd.DataFrame(results)
    os.makedirs("backtest", exist_ok=True)
    bt.to_csv("backtest/results_dow.csv", index=False, encoding="utf-8-sig")

    print("✅ Backtest saved: backtest/results_dow.csv")
    print(bt.tail(10))


# ===== Entry point =====
if __name__ == "__main__":
    # เทสต์ “ปี 2022” ตามที่คุยกัน
    run_dow_backtest(start_date="2022-01-01", end_date="2022-12-31")
