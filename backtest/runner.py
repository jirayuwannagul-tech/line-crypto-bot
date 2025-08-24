# backtest/runner.py  ← ใช้ไฟล์เดียว จัดเลเยอร์ให้ชัด

import sys, os, argparse, hashlib, inspect
import pandas as pd

# ===== Layer 0: Path & Imports =====
# ให้ import app/ ได้ (โฟลเดอร์นี้อยู่ระดับเดียวกับ backtest/)
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.analysis import dow


# ===== Layer 1: Data (โหลด + filter) =====
def load_data(path="app/data/historical.xlsx", start_date=None, end_date=None):
    df = pd.read_excel(path)

    # หาคอลัมน์ราคาปิด (ตามโค้ดเดิม)
    close_col = None
    for c in df.columns:
        if str(c).lower() in ["close", "closing price", "adj close"]:
            close_col = c
            break
    if close_col is None:
        raise RuntimeError(f"❌ ไม่เจอ column ราคาใน {path}, columns = {df.columns}")

    # ใช้ 'Date' ตามโค้ดเดิม (ไม่เปลี่ยน logic)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        if start_date and end_date:
            df = df.loc[start_date:end_date]

    return df, close_col


# ===== Layer 2: Logic (Helper + วิเคราะห์ทีละแท่ง) =====
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _get_close_series(df: pd.DataFrame):
    for c in df.columns:
        if str(c).lower() in ["close", "closing price", "adj close"]:
            return df[c]
    return None

def predict_trend_for_row(
    sub_df: pd.DataFrame,
    *,
    profile: str = "baseline",
    ema_short: int = 20,
    ema_long: int = 50,
    confirm_bars: int = 1
):
    """
    profile=baseline  -> ใช้ RULES อย่างเดียว (ค่าเริ่มต้น)
    profile=dow_ema   -> ใช้ EMA regime ครอบ RULES (logic layer, ไม่แตะ RULES)
    """
    # 1) RULES (ไม่แก้ไข)
    try:
        swings = dow.detect_swings(sub_df)
    except AttributeError:
        swings = (dow.analyze_dow(sub_df) if hasattr(dow, "analyze_dow") else {})
    rule_trend = swings.get("trend_primary", "SIDE")

    if profile != "dow_ema":
        return rule_trend

    # 2) LOGIC: EMA regime + confirm bars (ไม่แตะ RULES)
    close = _get_close_series(sub_df)
    if close is None or len(close) < max(ema_short, ema_long) + 2:
        # ถ้าข้อมูลไม่พอ ใช้ผล RULES ไปก่อน
        return rule_trend

    eS = _ema(close, ema_short)
    eL = _ema(close, ema_long)
    bias_now_up = eS.iat[-1] > eL.iat[-1]
    bias = "UP" if bias_now_up else "DOWN"

    # confirm bars: ต้องไม่เปลี่ยน bias ย้อนหลัง N แท่ง
    if confirm_bars > 1:
        if bias == "UP":
            stable = (eS.tail(confirm_bars) > eL.tail(confirm_bars)).all()
        else:
            stable = (eS.tail(confirm_bars) < eL.tail(confirm_bars)).all()
        if not stable:
            # ถ้าไม่เสถียร ใช้ bias ก่อนหน้า 1 แท่ง (ลด false flip)
            prev_bias = "UP" if eS.iat[-2] > eL.iat[-2] else "DOWN"
            bias = prev_bias

    # 3) ผสานผล: ถ้า RULES เป็น SIDE → ใช้ bias; ถ้า RULES ชัด → คงตาม RULES
    final_trend = rule_trend if rule_trend in ("UP", "DOWN") else bias
    return final_trend


# ===== Layer 3: Backtest (วน loop และประกอบผลลัพธ์) =====
def run_dow_backtest(
    start_date=None,
    end_date=None,
    data_path="app/data/historical.xlsx",
    *,
    profile="baseline",
    ema_short=20,
    ema_long=50,
    confirm_bars=1,
    no_cache=False
):
    df, close_col = load_data(data_path, start_date, end_date)

    results = []
    for i in range(50, len(df)):  # คง logic เดิม
        sub_df = df.iloc[:i].copy()
        trend_pred = predict_trend_for_row(
            sub_df,
            profile=profile,
            ema_short=ema_short,
            ema_long=ema_long,
            confirm_bars=confirm_bars,
        )

        # Label จริงจากแท่งถัดไป (ตามโค้ดเดิม)
        if i + 1 < len(df):
            real_trend = "UP" if df[close_col].iloc[i + 1] > df[close_col].iloc[i] else "DOWN"
        else:
            real_trend = None

        results.append({
            "date": df.index[i] if hasattr(df, "index") else i,
            "close": df[close_col].iloc[i],
            "trend_pred": trend_pred,
            "real_trend": real_trend,
            "hit": 1 if (trend_pred in ("UP", "DOWN") and trend_pred == real_trend) else 0
        })

    # ===== Layer 4: Report (บันทึก CSV + แสดงท้ายตาราง) =====
    bt = pd.DataFrame(results)
    os.makedirs("backtest", exist_ok=True)
    out_path = "backtest/results_dow.csv" if not no_cache else "backtest/results_dow_nocache.csv"
    bt.to_csv(out_path, index=False, encoding="utf-8-sig")

    print("✅ Backtest saved:", out_path)
    print(bt.tail(10))


# ===== Entry point =====
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="baseline", help="baseline | dow_ema")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2022-12-31")
    ap.add_argument("--ema-short", type=int, default=20)
    ap.add_argument("--ema-long", type=int, default=50)
    ap.add_argument("--confirm-bars", type=int, default=1)
    ap.add_argument("--data", default="app/data/historical.xlsx")
    args = ap.parse_args()

    # Logs ยืนยันว่าใช้โค้ด/โปรไฟล์ที่ถูกต้อง
    print("PY:", sys.executable)
    print("DOW_FILE:", getattr(dow, "__file__", "?"))
    print("LOGIC_VERSION(dow):", getattr(dow, "LOGIC_VERSION", "n/a"))
    print("LOGIC_FINGERPRINT(dow):", dow._logic_fingerprint() if hasattr(dow, "_logic_fingerprint") else "n/a")
    print(
        "PROFILE:", args.profile,
        "| EMA:", args.ema_short, args.ema_long,
        "| confirm_bars:", args.confirm_bars,
        "| no_cache:", args.no_cache
    )

    run_dow_backtest(
        start_date=args.start,
        end_date=args.end,
        data_path=args.data,
        profile=args.profile,
        ema_short=args.ema_short,
        ema_long=args.ema_long,
        confirm_bars=args.confirm_bars,
        no_cache=args.no_cache,
    )
