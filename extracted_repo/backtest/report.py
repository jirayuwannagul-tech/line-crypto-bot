# backtest/report.py
import pandas as pd

def generate_report(file_path="backtest/results_dow.csv"):
    df = pd.read_csv(file_path)

    required_cols = {"trend_pred", "real_trend", "hit"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError(f"❌ ขาดคอลัมน์จำเป็นใน {file_path}: {missing}")

    # ===== ภาพรวม (Overall) =====
    total = len(df)
    correct = int(df["hit"].sum())
    accuracy = (correct / total * 100) if total else 0.0

    print("=== 📊 Backtest Report (Analysis Only) ===")
    print(f"Signals: {total}")
    print(f"Correct Predictions: {correct}")
    print(f"Accuracy: {accuracy:.2f}%")

    # ===== แยกตามทิศทางที่ทำนาย (UP/DOWN/SIDE) =====
    print("\n— Accuracy by predicted trend —")
    for k, g in df.groupby("trend_pred", dropna=False):
        n = len(g)
        hit = int(g["hit"].sum())
        acc = (hit / n * 100) if n else 0.0
        print(f"{str(k):>5}: {acc:.2f}%  (n={n})")

    # ===== แยกตามปี (ถ้า parse วันที่ได้) =====
    # พยายามค้นหาคอลัมน์วันที่อัตโนมัติ: 'date' หรือ 'Date'
    date_col = None
    for c in df.columns:
        if str(c).lower() == "date":
            date_col = c
            break

    if date_col is not None:
        try:
            dt = pd.to_datetime(df[date_col], errors="raise")
            df["_year"] = dt.dt.year
            print("\n— Accuracy by year —")
            for y, g in df.groupby("_year"):
                n = len(g)
                hit = int(g["hit"].sum())
                acc = (hit / n * 100) if n else 0.0
                print(f"{y}: {acc:.2f}%  (n={n})")
        except Exception:
            pass  # ถ้า parse วันที่ไม่ได้ก็ข้ามส่วนนี้ไป

    # ===== กรองตามความมั่นใจ (ถ้ามีคอลัมน์ confidence) =====
    if "confidence" in df.columns:
        # เลือก threshold ตัวอย่าง 60/70/80
        print("\n— Accuracy by confidence threshold —")
        for th in (60, 70, 80):
            g = df[df["confidence"] >= th]
            n = len(g)
            if n == 0:
                print(f"conf ≥ {th}: - (n=0)")
                continue
            hit = int(g["hit"].sum())
            acc = (hit / n * 100)
            print(f"conf ≥ {th}: {acc:.2f}%  (n={n})")


if __name__ == "__main__":
    generate_report()
