import pandas as pd
from app.analysis import dow

def run_dow_backtest():
    # โหลดข้อมูลย้อนหลัง
    df = pd.read_excel("app/data/historical.xlsx")

    # เรียกใช้ logic Dow
    try:
        swings = dow.detect_swings(df)
    except AttributeError:
        # fallback ถ้าใน dow.py ชื่อฟังก์ชันไม่ตรง
        if hasattr(dow, "analyze_dow"):
            swings = dow.analyze_dow(df)
        else:
            raise RuntimeError("❌ dow.py ไม่มีฟังก์ชัน detect_swings หรือ analyze_dow")

    print("=== สัญญาณจาก Dow (Swing High/Low) ===")
    print(swings.head(20))   # แสดง 20 จุดแรก
    print("\nรวมทั้งหมด:", len(swings), "สัญญาณ")

if __name__ == "__main__":
    run_dow_backtest()
