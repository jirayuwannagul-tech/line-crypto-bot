import sys, os
import pandas as pd

# ✅ แก้ path ให้หา app เจอ ไม่ว่ารันจากไหน
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.analysis import dow


def run_dow_backtest():
    # โหลด historical data
    df = pd.read_excel("app/data/historical.xlsx")

    # ตรวจว่ามีฟังก์ชันอะไรใน dow.py
    try:
        swings = dow.detect_swings(df)
    except AttributeError:
        if hasattr(dow, "analyze_dow"):
            swings = dow.analyze_dow(df)
        else:
            raise RuntimeError("❌ dow.py ไม่มีฟังก์ชัน detect_swings หรือ analyze_dow")

    print("=== สัญญาณจาก Dow (Swing High/Low) ===")

    # แสดงผลลัพธ์ที่ได้
    if isinstance(swings, dict):
        for k, v in swings.items():
            print(f"\n[{k}]")
            if isinstance(v, list):
                print("จำนวน:", len(v))
                print("ตัวอย่าง:", v[:5])
            elif hasattr(v, "head"):
                print("DataFrame/Series:")
                print(v.head())
            else:
                print("ค่า:", v)
    else:
        print("ไม่ใช่ dict:", type(swings))
        print(swings.head(20) if hasattr(swings, "head") else swings)


if __name__ == "__main__":
    run_dow_backtest()
