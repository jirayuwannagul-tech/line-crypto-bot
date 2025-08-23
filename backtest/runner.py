import sys, os
import pandas as pd

# ✅ set path ให้หา app/ ได้
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.analysis import dow


def run_dow_backtest(start_date=None, end_date=None):
    # โหลดข้อมูล
    df = pd.read_excel("app/data/historical.xlsx")

    # หาชื่อ column ที่เป็นราคาปิด
    close_col = None
    for c in df.columns:
        if str(c).lower() in ["close", "closing price", "adj close"]:
            close_col = c
            break
    if close_col is None:
        raise RuntimeError(f"❌ ไม่เจอ column ราคาใน historical.xlsx, columns = {df.columns}")

    # ถ้ามี Date column → แปลงเป็น datetime และ filter ตามช่วงเวลา
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        if start_date and end_date:
            df = df.loc[start_date:end_date]

    results = []

    # 🟢 loop candle ทีละแท่ง
    for i in range(50, len(df)):
        sub_df = df.iloc[:i].copy()

        # ดึงสัญญาณจาก dow.py
        try:
            swings = dow.detect_swings(sub_df)
        except AttributeError:
            swings = (
                dow.analyze_dow(sub_df)
                if hasattr(dow, "analyze_dow")
                else {}
            )

        trend_pred = swings.get("trend_primary", None)

        # เทียบกับราคาจริงแท่งถัดไป
        if i + 1 < len(df):
            real_trend = (
                "UP"
                if df[close_col].iloc[i + 1] > df[close_col].iloc[i]
                else "DOWN"
            )
        else:
            real_trend = None

        results.append({
            "date": df.index[i] if hasattr(df, "index") else i,
            "close": df[close_col].iloc[i],
            "trend_pred": trend_pred,
            "real_trend": real_trend,
            "hit": 1 if trend_pred == real_trend else 0
        })

    # แปลงเป็น DataFrame และ save CSV
    bt = pd.DataFrame(results)
    bt.to_csv("backtest/results_dow.csv", index=False, encoding="utf-8-sig")

    print("✅ Backtest saved: backtest/results_dow.csv")
    print(bt.tail(10))


if __name__ == "__main__":
    # 🟢 ตัวอย่าง: backtest เฉพาะปี 2020–2021 (Bull market)
    run_dow_backtest(start_date="2020-01-01", end_date="2021-12-31")
