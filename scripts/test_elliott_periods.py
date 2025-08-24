import sys
import os
import pandas as pd
import json

# ============================================================
# [Layer 1] ตั้งค่า Python Path ให้เห็น root project
# ============================================================
# ทำให้ Python มองเห็นโฟลเดอร์ app/ ได้ เวลาที่เรา import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis import elliott as ew


# ============================================================
# [Layer 2] กำหนดข้อมูลการทดสอบ (Test Case)
# ============================================================
# รูปแบบ: (label, start_date, end_date, expected_wave)
# label        = ชื่อช่วงเวลา
# start_date   = วันที่เริ่ม
# end_date     = วันที่สิ้นสุด
# expected_wave= คลื่นที่คาดว่าจะเจอจริง
TEST_CASE = ("May 2021", "2021-05-01", "2021-05-31", "wave 5 end")


# ============================================================
# [Layer 3] โหลดข้อมูลราคาจาก historical.xlsx
# ============================================================
df = pd.read_excel("app/data/historical.xlsx")
df['date'] = pd.to_datetime(df['date'])  # แปลงวันที่ให้เป็น datetime

label, start, end, expected = TEST_CASE
mask = (df['date'] >= start) & (df['date'] <= end)
df_test = df.loc[mask].copy()  # เลือกเฉพาะช่วงเวลาที่สนใจ


# ============================================================
# [Layer 4] รัน Elliott Analyzer
# ============================================================
# วิเคราะห์คลื่น Elliott จากข้อมูลที่เลือก
waves = ew.analyze_elliott(df_test)

# สมมติ analyzer คืน list ของ wave → เราเลือก wave สุดท้ายมาเปรียบเทียบ
detected = waves[-1]["label"] if waves else "None"


# ============================================================
# [Layer 5] สรุปผลการทดสอบ
# ============================================================
# เปรียบเทียบว่า detected ตรงกับ expected หรือไม่
result = "✅ Correct" if expected.lower() in detected.lower() else "❌ Incorrect"

summary = {
    "period": label,
    "expected": expected,
    "detected": detected,
    "result": result
}


# ============================================================
# [Layer 6] เก็บผลลัพธ์ลง Log
# ============================================================
# ไฟล์ log เก็บผลการทดสอบทั้งหมด
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"

# ถ้ามีไฟล์ log อยู่แล้ว → โหลดมาก่อน
if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8") as f:
        logs = json.load(f)
else:
    logs = []

# เพิ่มผลลัพธ์รอบนี้เข้าไป
logs.append(summary)

# เขียนกลับลงไฟล์
with open(log_file, "w", encoding="utf-8") as f:
    json.dump(logs, f, indent=4, ensure_ascii=False)


# ============================================================
# [Layer 7] แสดงผลสรุปบน Console
# ============================================================
print("== Elliott Wave Test ==")
print(f"Period   : {label}")
print(f"Expected : {expected}")
print(f"Detected : {detected}")
print(f"Result   : {result}")
print(f"✅ Saved to {log_file}")
