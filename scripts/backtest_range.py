import pandas as pd
import argparse
from app.analysis import dow
import os

def backtest_range(df, start, end, save_path="backtest/results.csv"):
    records = []
    periods = pd.date_range(start=start, end=end, freq="M")

    for i in range(len(periods) - 1):
        analysis_start = periods[i].strftime("%Y-%m-01")
        analysis_end   = periods[i].strftime("%Y-%m-%d")
        forward_start  = periods[i+1].strftime("%Y-%m-01")
        forward_end    = periods[i+1].strftime("%Y-%m-%d")

        analysis_df = df[(df['timestamp'] >= analysis_start) & (df['timestamp'] <= analysis_end)]
        forward_df  = df[(df['timestamp'] >= forward_start) & (df['timestamp'] <= forward_end)]

        # ✅ debug log
        print(f"\nตรวจสอบช่วง {analysis_start} → {analysis_end}")
        print("analysis rows:", len(analysis_df), "| forward rows:", len(forward_df))

        if analysis_df.empty or forward_df.empty:
            print("⚠️ ข้ามช่วงนี้เพราะไม่มีข้อมูลครบ")
            continue

        result = dow.detect_swings(analysis_df)
        trend = result.get("trend_primary", "N/A")
        confidence = result.get("confidence", 0)

        start_price = forward_df.iloc[0]["open"]
        end_price   = forward_df.iloc[-1]["close"]
        real_trend = "UP" if end_price > start_price else "DOWN"

        hit = (trend == real_trend)

        records.append({
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "trend_pred": trend,
            "confidence": confidence,
            "forward_start": forward_start,
            "forward_end": forward_end,
            "real_trend": real_trend,
            "hit": int(hit)
        })

        print(f"ทำนาย: {trend} ({confidence}%)")
        print(f"ผลจริง {forward_start} → {forward_end}: {real_trend}")
        print("✅ ตรง" if hit else "❌ ไม่ตรง")

    # สรุปผล
    result_df = pd.DataFrame(records)
    if not result_df.empty:
        # ถ้าโฟลเดอร์ยังไม่มี ให้สร้างก่อน
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result_df.to_csv(save_path, index=False)
        print(f"\n✅ บันทึกผลลัพธ์ที่ {save_path}")
        accuracy = result_df["hit"].mean() * 100
        print("\n=== สรุป Backtest ===")
        print(f"จำนวนรอบ: {len(result_df)}")
        print(f"ตรง: {result_df['hit'].sum()} | ไม่ตรง: {len(result_df) - result_df['hit'].sum()}")
        print(f"ความแม่นยำ: {accuracy:.2f}%")
    else:
        print("⚠️ ไม่มีข้อมูลที่ทดสอบได้")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, required=True, help="วันเริ่มต้น เช่น 2019-01-01")
    parser.add_argument("--end", type=str, required=True, help="วันสิ้นสุด เช่น 2019-12-31")
    parser.add_argument("--out", type=str, default="backtest/results.csv", help="ไฟล์ผลลัพธ์")
    args = parser.parse_args()

    df = pd.read_excel("app/data/historical.xlsx")
    backtest_range(df, start=args.start, end=args.end, save_path=args.out)
