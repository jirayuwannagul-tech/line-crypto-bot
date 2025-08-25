import pandas as pd
from sklearn.metrics import confusion_matrix, classification_report

# โหลดไฟล์
df = pd.read_csv("backtest/results_elliott.csv")

# ความแม่นยำรวม
total = len(df)
correct = df['hit'].sum()
accuracy = correct / total * 100
print(f"Total: {total}, Correct: {correct}, Accuracy: {accuracy:.2f}%")

# ความแม่นยำแยกตามคลื่น
print("\nAccuracy by Wave Type:")
print(df.groupby("trend_pred")["hit"].mean() * 100)

# --- ✅ แก้ตรงนี้: บังคับให้เป็น string ---
y_true = df["real_trend"].astype(str)
y_pred = df["trend_pred"].astype(str)

# Confusion Matrix
print("\nConfusion Matrix:")
print(confusion_matrix(y_true, y_pred, labels=y_true.unique()))

print("\nClassification Report:")
print(classification_report(y_true, y_pred))
