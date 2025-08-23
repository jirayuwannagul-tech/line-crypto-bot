import pandas as pd
from app.analysis import dow

def run_dow_backtest():
    # โหลดข้อมูลย้อนหลัง
    df = pd.read_excel("app/data/historical.xlsx")

    # เรียกใช้ logic Dow
    try:
        swings = dow.detect_swings(df)
    except AttributeError:
        if hasattr(dow, "analyze_dow"):
            swings = dow.analyze_dow(df)
        else:
            raise RuntimeError("❌ dow.py ไม่มีฟังก์ชัน detect_swings หรือ analyze_dow")

    print("=== สัญญาณจาก Dow (Swing High/Low) ===")

    # ถ้าเป็น dict → print keys + ตัวอย่าง
    if isinstance(swings, dict):
        for k, v in swings.items():
            print(f"\n[{k}] → {len(v)} จุด")
            # ถ้าเป็น list → แสดง 5 ตัวแรก
            if isinstance(v, list):
                print("ตัวอย่าง:", v[:5])
            # ถ้าเป็น DataFrame/Series → ใช้ head()
            elif hasattr(v, "head"):
                print(v.head())
            else:
                print(v)
    else:
        # ถ้าไม่ใช่ dict เช่น DataFrame
        print(swings.head(20))
        print("\nรวมทั้งหมด:", len(swings), "สัญญาณ")

if __name__ == "__main__":
    run_dow_backtest()
