import pandas as pd

def show_history(file_path="app/data/historical.xlsx", n=5):
    df = pd.read_excel(file_path)

    print("=== 5 แถวแรก ===")
    print(df.head(n))
    print("\n=== 5 แถวสุดท้าย ===")
    print(df.tail(n))
    print("\n=== คอลัมน์ที่มีอยู่ ===")
    print(df.columns.tolist())
    print("\n=== รูปร่างข้อมูล (rows, cols) ===")
    print(df.shape)
    print("\n=== สรุปสถิติ ===")
    print(df.describe())

if __name__ == "__main__":
    show_history()
