import pandas as pd
import argparse
from app.analysis import dow
import os

def _call_dow(df):
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # รองรับหลายชื่อฟังก์ชัน
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
        out["trend_primary"]   = res.get("trend_primary") or res.get("trend") or res.get("primary")
        out["trend_secondary"] = res.get("trend_secondary") or res.get("secondary")
        out["confidence"]      = res.get("confidence") or res.get("score") or res.get("prob")
    elif isinstance(res, (list, tuple)) and len(res) >= 1:
        out["trend_primary"] = res[0]
        if len(res) > 1: out["confidence"] = res[1]
    elif isinstance(res, str):
        out["trend_primary"] = res
    else:
        out["trend_primary"] = str(res)

    if out["trend_primary"] is None:
        raise RuntimeError(f"อ่านผลลัพธ์ Dow ไม่ได้: {res}")

    if isinstance(out["trend_primary"], str):
        out["trend_primary"] = out["trend_primary"].strip().upper()

    # default confidence ถ้าไม่มี ให้เป็น 0
    if out["confidence"] is None:
        out["confidence"] = 0
    return out

def backtest_range(df, start, end, save_path="backtest/results.csv", min_conf=0, skip_side=True):
    # ensure datetime + sort
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    records = []
    periods = pd.date_range(start=start, end=end, freq="ME")  # month-end
    skipped = 0

    for i in range(len(periods) - 1):
        analysis_start = periods[i].replace(day=1).strftime("%Y-%m-%d")
        analysis_end   = periods[i].strftime("%Y-%m-%d")
        forward_start  = periods[i+1].replace(day=1).strftime("%Y-%m-%d")
        forward_end    = periods[i+1].strftime("%Y-%m-%d")

        analysis_df = df[(df['timestamp'] >= analysis_start) & (df['timestamp'] <= analysis_end)]
        forward_df  = df[(df['timestamp'] >= forward_start) & (df['timestamp'] <= forward_end)]

        print(f"\nตรวจสอบช่วง {analysis_start} → {analysis_end}")
        print("analysis rows:", len(analysis_df), " | forward rows:", len(forward_df))

        if analysis_df.empty or forward_df.empty:
            print("⚠️ ข้ามช่วงนี้เพราะไม่มีข้อมูลครบ")
            continue

        res = _call_dow(analysis_df)
        trend = (res.get("trend_primary") or "N/A").upper()
        confidence = float(res.get("confidence") or 0)

        start_price = float(forward_df.iloc[0]["open"])
        end_price   = float(forward_df.iloc[-1]["close"])
        real_trend = "UP" if end_price > start_price else "DOWN"

        actionable = True
        reason = ""
        if skip_side and trend in {"SIDE", "NEUTRAL", "FLAT"}:
            actionable = False
            reason = "SIDE"
        if confidence < min_conf:
            actionable = False
            reason = (reason + "; " if reason else "") + f"CONF<{min_conf}"

        hit = (trend == real_trend) if actionable else None

        records.append({
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "trend_pred": trend,
            "confidence": confidence,
            "forward_start": forward_start,
            "forward_end": forward_end,
            "real_trend": real_trend,
            "actionable": int(actionable),
            "hit": (int(hit) if hit is not None else ""),
            "skip_reason": reason
        })

        if actionable:
            print(f"ทำนาย: {trend} ({confidence:.0f}%) | ผลจริง {forward_start}→{forward_end}: {real_trend}")
            print("✅ ตรง" if hit else "❌ ไม่ตรง")
        else:
            skipped += 1
            print(f"ℹ️ ไม่คิดรอบนี้ในความแม่นยำ (trend={trend}, conf={confidence:.0f}%) → {reason}")

    # สรุปผล
    result_df = pd.DataFrame(records)
    if not result_df.empty:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result_df.to_csv(save_path, index=False)
        print(f"\n✅ บันทึกผลลัพธ์ที่ {save_path}")

        used = result_df[result_df["actionable"] == 1]
        if not used.empty:
            acc = (used["hit"].astype(int).mean()) * 100
            print("\n=== สรุป Backtest (เฉพาะสัญญาณที่ใช้เทรดได้) ===")
            print(f"จำนวนรอบทั้งหมด: {len(result_df)} | ใช้งานได้: {len(used)} | ถูกข้าม: {skipped}")
            print(f"ตรง: {used['hit'].sum()} | ไม่ตรง: {len(used) - used['hit'].sum()}")
            print(f"ความแม่นยำ: {acc:.2f}%")
        else:
            print("\n⚠️ ไม่มีสัญญาณที่เข้าเงื่อนไขนำมาคิดความแม่นยำ")
    else:
        print("⚠️ ไม่มีข้อมูลที่ทดสอบได้")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--out", type=str, default="backtest/results.csv")
    parser.add_argument("--min-conf", type=float, default=0, help="ขั้นต่ำความมั่นใจ เพื่อตัดสัญญาณทิ้งจากสถิติ")
    parser.add_argument("--no-skip-side", action="store_true", help="ถ้าใส่ flag นี้ จะนับ SIDE เป็นสัญญาณด้วย")
    args = parser.parse_args()

    df = pd.read_excel("app/data/historical.xlsx")
    backtest_range(
        df,
        start=args.start,
        end=args.end,
        save_path=args.out,
        min_conf=args.min_conf,
        skip_side=not args.no_skip_side
    )
