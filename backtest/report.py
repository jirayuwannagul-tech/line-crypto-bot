import pandas as pd

def generate_report(file_path="backtest/results_dow.csv"):
    df = pd.read_csv(file_path)

    total = len(df)
    correct = df["hit"].sum()
    accuracy = correct / total * 100 if total > 0 else 0

    # สมมติกลยุทธ์: ถ้า pred=UP → long, ถ้า pred=DOWN → short
    pnl = []
    balance = 10000  # เริ่มต้น 10k
    peak = balance
    drawdowns = []

    for i in range(len(df) - 1):
        pred, real = df.loc[i, "trend_pred"], df.loc[i, "real_trend"]

        if pred == real:
            balance *= 1.01  # +1% ถ้าถูก
        else:
            balance *= 0.99  # -1% ถ้าผิด

        peak = max(peak, balance)
        drawdown = (balance - peak) / peak * 100
        drawdowns.append(drawdown)
        pnl.append(balance)

    winrate = df["hit"].mean() * 100
    max_drawdown = min(drawdowns) if drawdowns else 0

    print("=== 📊 Backtest Report ===")
    print(f"Signals: {total}")
    print(f"Accuracy: {accuracy:.2f}%")
    print(f"Winrate: {winrate:.2f}%")
    print(f"Max Drawdown: {max_drawdown:.2f}%")
    print(f"Final Balance: {balance:.2f} USDT")

if __name__ == "__main__":
    generate_report()
