import pandas as pd

# โหลดไฟล์ผล backtest
df = pd.read_csv("backtest/results_elliott.csv")

# --- 1) สร้าง mapping จากคลื่น -> ทิศทางตลาด ---
mapping = {
    "IMPULSE_PROGRESS": "UP",
    "IMPULSE_TOP": "UP",
    "CORRECTION": "DOWN"
}

# แปลง prediction จาก Elliott wave ให้เป็นทิศทาง
df["pred_direction"] = df["trend_pred"].map(mapping).fillna("UNKNOWN")

# --- 2) คำนวณ hit ใหม่ (เปรียบเทียบกับ real_trend: UP/DOWN) ---
df["hit_mapped"] = (df["pred_direction"] == df["real_trend"]).astype(int)

# --- 3) ความแม่นยำรวม ---
total = len(df)
correct = df["hit_mapped"].sum()
accuracy = correct / total * 100

print("===== Elliott Wave Backtest (Mapped to UP/DOWN) =====")
print(f"Total: {total}")
print(f"Correct: {correct}")
print(f"Accuracy: {accuracy:.2f}%")

# --- 4) ความแม่นยำแยกตาม pred_direction ---
print("\nAccuracy by Direction:")
print(df.groupby("pred_direction")["hit_mapped"].mean() * 100)

# --- 5) Confusion Table (เปรียบเทียบจริง vs ทำนาย) ---
print("\nConfusion Table (Actual vs Predicted):")
print(pd.crosstab(df["real_trend"], df["pred_direction"], rownames=["Actual"], colnames=["Predicted"]))

# --- 6) แสดงตัวอย่างผลลัพธ์บางส่วน ---
print("\nSample Predictions:")
print(df[["date", "trend_pred", "pred_direction", "real_trend", "hit_mapped"]].head(20))
