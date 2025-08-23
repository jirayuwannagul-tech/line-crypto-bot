import pandas as pd
import os

FILE_PATH = "app/data/historical.xlsx"

def check_data(file_path=FILE_PATH, start=None, end=None):
    if not os.path.exists(file_path):
        print(f"❌ ไม่พบไฟล์ {file_path}")
        return

    df = pd.read_excel(file_path)
    print(f"✅ พบไฟล์ {file_path}")
    print("คอลัมน์:", df.columns.tolist())
    print("จำนวนแถวทั้งหมด:", len(df))

    if start and end:
        subset = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]
        print(f"\nช่วง {start} → {end}")
        print("จำนวนข้อมูล:", len(subset))
        if not subset.empty:
            print(subset.head())
            print(subset.tail())
        else:
            print("⚠️ ไม่มีข้อมูลในช่วงนี้")

if __name__ == "__main__":
    # ตัวอย่าง: เช็กช่วงปี 2019
    check_data(start="2019-01-01", end="2019-12-31")
