import pandas as pd
import json
import os
from app.analysis import elliott as ew

# =============================
# กำหนดข้อมูลการทดสอบแต่ละครั้ง
# =============================
# 👉 ตัวอย่าง: (label, start_date, end_date, expected_wave)
TEST_CASE = ("May 2021", "2021-05-01", "2021-05-31", "wave 5 end")

# =============================
# โหลดข้อมูลจาก historical.xlsx
# =============================
df = pd.read_excel("app/data/historical.xlsx")
df['date'] = pd.to_datetime(df['date'])

label, start, end, expected = TEST_CASE
mask = (df['date'] >= start) & (df['date'] <= end)
df_test = df.loc[mask].copy()

# =============================
# รัน Elliott Analyzer
# =============================
waves = ew.analyze_elliott(df_test)

# สมมติว่า analyzer คืนผลเป็น list ให้เราเลือก wave สุดท้าย
detected = waves[-1]["label"] if waves else "None"

# =============================
# สรุปผล
# =============================
result = "✅ Correct" if expected.lower() in detected.lower() else "❌ Incorrect"

summary = {
    "period": label,
    "expected": expected,
    "detected": detected,
    "result": result
}

# =============================
# เก็บผลลัพธ์ (append ลง log)
# =============================
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"

# ถ้ามีไฟล์แล้ว → โหลดมาก่อน
if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8") as f:
        logs = json.load(f)
else:
    logs = []

logs.append(summary)

with open(log_file, "w", encoding="utf-8") as f:
    json.dump(logs, f, indent=4, ensure_ascii=False)

print("== Elliott Wave Test ==")
print(f"Period   : {label}")
print(f"Expected : {expected}")
print(f"Detected : {detected}")
print(f"Result   : {result}")
print(f"✅ Saved to {log_file}")

