import pandas as pd
from sklearn.metrics import confusion_matrix, classification_report

# 1) โหลดไฟล์ผล backtest (แก้ path ถ้าไฟล์คุณอยู่ที่อื่น)
df = pd.read_csv("backtest/results_elliott.csv")

# 2) ความแม่นยำรวม
total = len(df)
correct = df['hit'].sum()
accuracy = correct / total * 100
print(f"Total: {total}, Correct: {correct}, Accuracy: {accuracy:.2f}%")

# 3) ความแม่นยำแยกตามคลื่น
print("\nAccuracy by Wave Type:")
print(df.groupby("trend_pred")["hit"].mean() * 100)

# 4) Confusion Matrix
y_true = df["real_trend"]
y_pred = df["trend_pred"]

print("\nConfusion Matrix:")
print(confusion_matrix(y_true, y_pred, labels=y_true.unique()))

print("\nClassification Report:")
print(classification_report(y_true, y_pred))

