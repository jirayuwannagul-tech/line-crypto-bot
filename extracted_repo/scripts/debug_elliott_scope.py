import pandas as pd
from app.logic.elliott_logic import classify_elliott
from app.analysis.elliott import _build_swings

def debug_elliott_scope(df: pd.DataFrame):
    print("=== ตรวจสอบขอบเขตการวิเคราะห์ Elliott Wave ===")
    print(f"จำนวนแท่งเทียนทั้งหมด: {len(df)}")
    if "timestamp" in df.columns:
        print(f"ช่วงวันที่ที่ใช้วิเคราะห์: {df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}")
    else:
        print("ช่วงที่ใช้วิเคราะห์: index 0 → index", len(df)-1)

    # ตรวจสอบจุดสวิง (Swings)
    swings = _build_swings(df)
    print(f"จำนวนสวิงที่ตรวจพบ: {len(swings)}")
    if not swings.empty:
        print("สวิงแรก   :", swings.iloc[0].to_dict())
        print("สวิงล่าสุด:", swings.iloc[-1].to_dict())

    # ใช้ logic layer (classify_elliott)
    res = classify_elliott(df)
    print("\n=== ผลการวิเคราะห์ Elliott Wave ===")
    print("รูปแบบ (Pattern):", res["pattern"])
    print("ทิศทาง (Direction):", res["current"]["direction"])
    print("ครบรูปแบบหรือยัง (Completed):", res["completed"])
    print("จำนวนกฎที่ตรวจสอบ:", len(res.get("rules", [])))
    print("จำนวนสวิงที่ใช้วิเคราะห์:", len(res.get("debug", {}).get("swings", [])))


if __name__ == "__main__":
    # 🔹 ตัวอย่างข้อมูลเล็ก ๆ
    data = {
        "high":  [100, 105, 102, 110, 108, 115, 113, 118],
        "low":   [ 95,  98,  96, 100,  99, 105, 107, 112],
        "close": [ 98, 103,  97, 109, 107, 112, 111, 117],
    }
    df = pd.DataFrame(data)

    debug_elliott_scope(df)
