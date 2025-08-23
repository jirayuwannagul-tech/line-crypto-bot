import pandas as pd

INPUT = "backtest/results_fib.csv"

def report():
    df = pd.read_csv(INPUT)
    if df.empty:
        print("No trades."); return

    total_setups = len(df)
    entered = (df["entered"] == 1).sum()
    tp = (df["result"] == "TP").sum()
    sl = (df["result"] == "SL").sum()
    timeout = (df["result"] == "TIMEOUT").sum()

    print("=== 📊 Fibonacci Pullback Backtest (Analysis Only) ===")
    print(f"Total setups: {total_setups}")
    print(f"Entered: {entered}")
    print(f"TP: {tp} | SL: {sl} | TIMEOUT: {timeout}")
    acc = (tp / entered * 100) if entered else 0.0
    print(f"Hit Rate (TP/Entered): {acc:.2f}%")

    # แยกตามฝั่ง
    for side, g in df.groupby("setup_dir"):
        ent = (g["entered"] == 1).sum()
        tp_ = (g["result"] == "TP").sum()
        sl_ = (g["result"] == "SL").sum()
        to_ = (g["result"] == "TIMEOUT").sum()
        hit = (tp_ / ent * 100) if ent else 0.0
        print(f"\n— {side.upper()} —")
        print(f"Entered: {ent} | TP: {tp_} | SL: {sl_} | TIMEOUT: {to_}")
        print(f"Hit Rate: {hit:.2f}%")

if __name__ == "__main__":
    report()
