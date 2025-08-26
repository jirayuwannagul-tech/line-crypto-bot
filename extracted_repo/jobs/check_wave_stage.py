# jobs/check_wave_stage.py
import pandas as pd
from app.analysis import elliott

def main():
    # โหลด historical data ล่าสุดที่ daily_btc_analysis.py เขียนไว้
    df = pd.read_excel("app/data/historical.xlsx", sheet_name="BTCUSDT_1D")

    # วิเคราะห์ Elliott Wave
    result = elliott.analyze_elliott(df)

    print("== Elliott Wave Analysis ==")
    print(f"Pattern:   {result.get('pattern')}")
    print(f"Completed: {result.get('completed')}")
    print(f"Current:   {result.get('current')}")
    print(f"Next:      {result.get('next')}")
    print(f"Targets:   {result.get('targets')}")

if __name__ == "__main__":
    main()
