import sys, os
import pandas as pd

# ✅ set path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.analysis import dow


def run_dow_backtest():
    df = pd.read_excel("app/data/historical.xlsx")
    results = []

    for i in range(50, len(df)):
        sub_df = df.iloc[:i].copy()

        try:
            swings = dow.detect_swings(sub_df)
        except AttributeError:
            swings = (
                dow.analyze_dow(sub_df)
                if hasattr(dow, "analyze_dow")
                else {}
            )

        trend_pred = swings.get("trend_primary", None)

        # เทียบกับราคาจริงแท่งถัดไป
        if i + 1 < len(df):
            real_trend = (
                "UP"
                if df["Close"].iloc[i + 1] > df["Close"].iloc[i]
                else "DOWN"
            )
        else:
            real_trend = None

        results.append({
            "date": df.index[i] if hasattr(df, "index") else i,
            "close": df["Close"].iloc[i],
            "trend_pred": trend_pred,
            "real_trend": real_trend,
            "hit": 1 if trend_pred == real_trend else 0
        })

    bt = pd.DataFrame(results)
    bt.to_csv("backtest/results_dow.csv", index=False, encoding="utf-8-sig")

    print("✅ Backtest saved: backtest/results_dow.csv")
    print(bt.tail(10))


if __name__ == "__main__":
    run_dow_backtest()
