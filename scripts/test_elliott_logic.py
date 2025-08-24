import pandas as pd
from app.logic.elliott_logic import classify_elliott

# ✅ ตัวอย่างกราฟที่มี high/low สลับกัน (ควรเจอ Impulse หรือ Zigzag ได้บ้าง)
data = {
    "high":  [100, 105, 102, 110, 108, 115, 113],
    "low":   [ 95,  98,  96, 100,  99, 105, 107],
    "close": [ 98, 103,  97, 109, 107, 112, 111],
}
df = pd.DataFrame(data)

res = classify_elliott(df)
print("=== Elliott Logic Test ===")
print("Pattern   :", res["pattern"])
print("Direction :", res["current"]["direction"])
print("Completed :", res["completed"])
print("Rules     :", len(res["rules"]))

