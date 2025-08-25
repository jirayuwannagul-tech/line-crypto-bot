# backtest/runner.py
# =============================================================================
# Backtest Runner (Dow Theory + Elliott Wave)
# -----------------------------------------------------------------------------
# Layer 0: Imports & Path setup
# Layer 1: Data loader
# Layer 2: Predictors (Dow / Elliott)
# Layer 3: Backtest loop
# Layer 4: Entry point (CLI)
# =============================================================================

import sys, os, argparse
import pandas as pd
from tqdm import tqdm   # ✅ progress bar

# ===== Layer 0: Path & Imports =====
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.analysis import dow
from app.logic import elliott_logic


# ===== Layer 1: Data Loader =====
def load_data(path="app/data/historical.xlsx", start_date=None, end_date=None):
    """
    โหลด historical data จาก Excel รองรับทั้งคอลัมน์ Date และ timestamp
    """
    df = pd.read_excel(path)

    # normalize datetime
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
    else:
        raise RuntimeError(f"❌ ไม่เจอ column วันที่ใน {path}, columns = {df.columns}")

    # filter by date
    if start_date and end_date:
        df = df.loc[start_date:end_date]

    return df


# ===== Layer 2: Predictors =====
def predict_dow(sub_df: pd.DataFrame, profile="baseline", ema_short=20, ema_long=50, confirm_bars=1):
    """
    วิเคราะห์แนวโน้มด้วย Dow Theory (+ EMA regime option)
    """
    try:
        swings = dow.detect_swings(sub_df)
    except AttributeError:
        swings = dow.analyze_dow(sub_df) if hasattr(dow, "analyze_dow") else {}
    return swings.get("trend_primary", "SIDE")


def predict_elliott(sub_df: pd.DataFrame):
    """
    วิเคราะห์รูปแบบด้วย Elliott Wave logic
    """
    res = elliott_logic.classify_elliott(sub_df)
    return res.get("kind", "UNKNOWN")


# ===== Layer 3: Backtest Loop =====
def run_backtest(
    mode="dow",
    start_date=None,
    end_date=None,
    data_path="app/data/historical.xlsx",
    **kwargs
):
    df = load_data(data_path, start_date, end_date)

    # เลือกคอลัมน์ close
    close = None
    for c in df.columns:
        if str(c).lower() in ["close", "closing price", "adj close"]:
            close = df[c]
            break
    if close is None:
        raise RuntimeError("❌ ไม่เจอ column close")

    results = []
    for i in tqdm(range(50, len(df)), desc=f"Running {mode} backtest"):  # ✅ progress bar
        sub_df = df.iloc[:i].copy()

        if mode == "dow":
            trend_pred = predict_dow(sub_df, **kwargs)
        else:  # Elliott mode
            sub_df = sub_df.tail(600)   # ✅ จำกัดข้อมูลล่าสุด 600 แท่ง
            trend_pred = predict_elliott(sub_df)

        if i + 1 < len(df):
            real_trend = "UP" if close.iloc[i + 1] > close.iloc[i] else "DOWN"
        else:
            real_trend = None

        results.append({
            "date": df.index[i],
            "close": float(close.iloc[i]),
            "trend_pred": trend_pred,
            "real_trend": real_trend,
            "hit": 1 if trend_pred in ("UP", "DOWN") and trend_pred == real_trend else 0,
        })

    bt = pd.DataFrame(results)
    os.makedirs("backtest", exist_ok=True)
    out_path = f"backtest/results_{mode}.csv"
    bt.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"\n✅ Backtest ({mode}) saved:", out_path)
    print(bt.tail(10))


# ===== Layer 4: Entry Point (CLI) =====
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="dow", choices=["dow", "elliott"], help="เลือกโหมด backtest: dow | elliott")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--data", default="app/data/historical.xlsx")
    ap.add_argument("--ema-short", type=int, default=20)
    ap.add_argument("--ema-long", type=int, default=50)
    ap.add_argument("--confirm-bars", type=int, default=1)
    args = ap.parse_args()

    run_backtest(
        mode=args.mode,
        start_date=args.start,
        end_date=args.end,
        data_path=args.data,
        profile="baseline",
        ema_short=args.ema_short,
        ema_long=args.ema_long,
        confirm_bars=args.confirm_bars,
    )
