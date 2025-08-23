import pandas as pd
import argparse
from app.analysis import dow
import os

def _call_dow(df):
    """
    พยายามเรียกฟังก์ชันที่มีอยู่จริงใน app.analysis.dow แล้ว normalize ผลลัพธ์
    ให้กลับมาเป็น dict: {"trend_primary": str, "trend_secondary": str|None, "confidence": int|float|None}
    """
    # เรียงเวลาและแปลง timestamp เผื่อเป็น string
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    if hasattr(dow, "detect_swings"):
        res = dow.detect_swings(df)
    elif hasattr(dow, "detect_trend"):
        res = dow.detect_trend(df)
    elif hasattr(dow, "analyze_dow"):
        res = dow.analyze_dow(df)
    else:
        raise RuntimeError("dow.py ไม่มี detect_swings / detect_trend / analyze_dow")

    out = {"trend_primary": None, "trend_secondary": None, "confidence": None}

    if isinstance(res, dict):
        # ชื่อ key ยอดฮิต
        out["trend_primary"] = res.get("trend_primary") or res.get("trend") or res.get("primary")
        out["trend_secondary"] = res.get("trend_secondary") or res.get("secondary")
        out["confidence"] = res.get("confidence") or res.get("score") or res.get("prob")
    elif isinstance(res, (list, tuple)) and len(res) >= 1:
        out["trend_primary"] = res[0]
        if len(res) > 1: out["confidence"] = res[1]
    elif isinstance(res, str):
        out["trend_primary"] = res
    else:
        # สุดท้ายพยายามแปลงเป็นสตริง
        out["trend_primary"] = str(res)

    if out["trend_primary"] is None:
        raise RuntimeError(f"อ่านผลลัพธ์ Dow ไม่ได้: {res}")

    # ปรับรูปแบบตัวพิมพ์ให้เทียบง่าย
    if isinstance(out["trend_primary"], str):
        out["trend_primary"] = out["trend_primary"].strip().upper()

    return out

def backtest_range(df, start, end, save_path="backtest/results.csv"):
    # ensure datetime + sort
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    records = []
    periods = pd.date_range(start=start, end=end, freq="ME")  # month-end

    for i in range(len(periods) - 1):
        analysis_start = periods[i].replace(day=1).strftime("%Y-%m-%d")
        analysis_end   = periods[i].strftime("%Y-%m-%d")
        forward_start  = periods[i+1].replace(day=1).strftime("%Y-%m-%d")
        forward_end    = periods[i+1].strftime("%Y-%m-%d")

        analysis_df = df[(df['timestamp'] >= analysis_start) & (df['timestamp'] <= analysis_end)]
        forward_df  = df[(df['timestamp'] >= forward_start) & (df['timestamp'] <= forward_end)]

        print(f"\nตรวจสอบช่วง {analysis_start} → {analysis_end}")
        print("analysis rows:", len(analysis_df), "| forward rows:", len(forward_df))

        if analysis_df.empty or forward_df.empty:
            print("⚠️ ข้ามช่วงนี้เพราะไม่มีข้อมูลครบ")
            continue

        res = _call_dow(analysis_df)
        trend = res.get("trend_primary", "N/A")
        confidence = res.get("confidence", 0)

        start_price = float(forward_df.iloc[0]["open"])
        end_price   = float(forward_df.iloc[-1]["close"])
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

    result_df = pd.DataFrame(records)
    if not result_df.empty:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result_df.to_csv(save_path, index=False)
        print(f"\n✅ บันทึกผลลัพธ์ที่ {save_path}")
        acc = result_df["hit"].mean() * 100
        print("\n=== สรุป Backtest ===")
        print(f"จำนวนรอบ: {len(result_df)}")
        print(f"ตรง: {result_df['hit'].sum()} | ไม่ตรง: {len(result_df) - result_df['hit'].sum()}")
        print(f"ความแม่นยำ: {acc:.2f}%")
    else:
        print("⚠️ ไม่มีข้อมูลที่ทดสอบได้")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, required=True, help="วันเริ่ม เช่น 2019-01-01")
    parser.add_argument("--end", type=str, required=True, help="วันสิ้นสุด เช่น 2019-12-31")
    parser.add_argument("--out", type=str, default="backtest/results.csv", help="ไฟล์ผลลัพธ์")
    args = parser.parse_args()

    df = pd.read_excel("app/data/historical.xlsx")
    backtest_range(df, start=args.start, end=args.end, save_path=args.out)
