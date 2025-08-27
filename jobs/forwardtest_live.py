# jobs/forwardtest_live.py
import argparse
import os
import subprocess
import pandas as pd

def find_csv(symbol: str, tf: str) -> str:
    cands = [f"data/{symbol}_{tf}.csv", f"app/data/{symbol}_{tf}.csv"]
    for p in cands:
        if os.path.exists(p):
            return p
    raise SystemExit(f"❌ ไม่พบไฟล์ราคา: {cands}")

def read_last_date(csv_path: str):
    # หา column เวลาแบบยืดหยุ่น
    df_head = pd.read_csv(csv_path, nrows=5)
    lower2orig = {c.lower(): c for c in df_head.columns}
    for k in ["time", "timestamp", "open_time", "date", "datetime"]:
        if k in lower2orig:
            time_col = lower2orig[k]
            break
    else:
        raise SystemExit(f"❌ ไม่พบคอลัมน์เวลาใน {csv_path}: {list(df_head.columns)}")

    col = pd.read_csv(csv_path, usecols=[time_col])[time_col]
    if pd.api.types.is_numeric_dtype(col):
        unit = "ms" if col.max() > 10**12 else "s"
        t = pd.to_datetime(col, unit=unit, errors="coerce")
    else:
        t = pd.to_datetime(col, errors="coerce")
    if t.isna().all():
        raise SystemExit("❌ เวลาเป็น NaT ทั้งหมด")
    return t.max().date()

def main():
    ap = argparse.ArgumentParser(description="Run forward test live until target end.")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="1H", choices=["1H","4H","1D"])
    ap.add_argument("--start", default="2025-09-01")       # จุดเริ่ม forward จริง
    ap.add_argument("--target-end", default="2025-11-01")  # สิ้นสุดเป้า
    ap.add_argument("--tp", type=float, default=0.008)
    ap.add_argument("--sl", type=float, default=0.008)
    ap.add_argument("--horizon", type=int, default=24)
    ap.add_argument("--min-bars", type=int, default=20)
    ap.add_argument("--adx-min", type=float, default=0.0)
    ap.add_argument("--out", default="output/forwardtest_live_window.csv")
    args = ap.parse_args()

    csv_path = find_csv(args.symbol, args.tf)
    data_last = read_last_date(csv_path)
    target_end = pd.to_datetime(args.target_end).date()
    dyn_end = min(data_last, target_end)

    # ✅ Guard: ถ้ายังไม่มีข้อมูลถึงช่วงที่อยากเริ่ม → เขียนไฟล์ว่างและจบ
    start_date = pd.to_datetime(args.start).date()
    if dyn_end < start_date:
        os.makedirs("output", exist_ok=True)
        pd.DataFrame().to_csv(args.out, index=False)
        print(f"⏳ ยังไม่มีข้อมูลถึง {start_date}. เขียนไฟล์ว่าง: {args.out}")
        return

    os.makedirs("output", exist_ok=True)
    cmd = [
        "python", "scripts/forward_test.py",
        "--symbol", args.symbol,
        "--tf", args.tf,
        "--start", args.start,
        "--end", str(dyn_end),
        "--tp", str(args.tp),
        "--sl", str(args.sl),
        "--horizon", str(args.horizon),
        "--min-bars", str(args.min_bars),
        "--out", args.out
    ]
    if args.adx_min and float(args.adx_min) > 0:
        cmd += ["--adx-min", str(args.adx_min)]

    print(f"📅 Data last = {data_last} | target_end = {target_end} | use END = {dyn_end}")
    print("▶️", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        raise SystemExit(f"❌ forward_test.py exit code {rc}")
    print(f"✅ saved -> {args.out}")

if __name__ == "__main__":
    main()
