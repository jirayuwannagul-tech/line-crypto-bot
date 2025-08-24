# scripts/test_elliott_periods.py
# ============================================================
# Test Elliott detection across sample periods
# - ใช้ logic layer จริง: classify_elliott_with_kind()
# - ไม่ยัด rule ในไฟล์เทสอีกต่อไป
# ============================================================

import sys, os, json
import pandas as pd

# ให้ Python เห็น root project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# logic ที่เป็นสมองจริง
try:
    from app.logic.elliott_logic import classify_elliott_with_kind as logic_classify
except Exception as e:
    raise ImportError(f"ไม่พบ app.logic.elliott_logic.classify_elliott_with_kind: {e}")

# -------------------- Test cases --------------------
TEST_CASES = [
    ("Oct 2020", "2020-10-01", "2020-10-31", "IMPULSE_PROGRESS"),
    ("Jan 2021", "2021-01-01", "2021-01-31", "IMPULSE_PROGRESS"),
    ("Apr 2021", "2021-04-01", "2021-04-30", "IMPULSE_TOP"),
    ("May 2021", "2021-05-01", "2021-05-31", "IMPULSE_TOP"),
    ("Sep 2021", "2021-09-01", "2021-09-30", "IMPULSE_PROGRESS"),
    ("Nov 2021", "2021-11-01", "2021-11-30", "IMPULSE_TOP"),
    ("Jan 2022", "2022-01-01", "2022-01-31", "CORRECTION"),
    ("Jun 2022", "2022-06-01", "2022-06-30", "CORRECTION"),
    ("Aug 2022", "2022-08-01", "2022-08-31", "CORRECTION"),
    ("Nov 2022", "2022-11-01", "2022-11-30", "CORRECTION"),
]
TF_LIST = ["1D", "4H", "1H"]

# -------------------- Data helpers --------------------
DATE_CANDIDATES = ["date","Date","timestamp","Timestamp","time","Time","open_time","Open time","Datetime","datetime"]
OHLC_MAPS = [
    {"Open":"open","High":"high","Low":"low","Close":"close"},
    {"open":"open","high":"high","low":"low","close":"close"},
    {"OPEN":"open","HIGH":"high","LOW":"low","CLOSE":"close"},
]

def load_df(path: str) -> pd.DataFrame:
    obj = pd.read_excel(path, sheet_name=None)
    if isinstance(obj, dict):
        df = obj[list(obj)[0]]
    else:
        df = obj
    return df.copy()

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    date_col = next((c for c in DATE_CANDIDATES if c in cols), None)
    if not date_col:
        lower = {c.lower(): c for c in cols}
        for cand in [c.lower() for c in DATE_CANDIDATES]:
            if cand in lower:
                date_col = lower[cand]; break
    if not date_col:
        raise KeyError(f"ไม่พบคอลัมน์วันที่ใน {cols}")

    out = df.rename(columns={date_col:"date"}).copy()
    out["date"] = pd.to_datetime(out["date"], utc=False, errors="coerce")

    for m in OHLC_MAPS:
        if len([k for k in m if k in out.columns]) >= 3:
            out = out.rename(columns=m)

    if "close" not in out.columns and "Adj Close" in out.columns:
        out = out.rename(columns={"Adj Close":"close"})

    miss = [c for c in ["open","high","low","close"] if c not in out.columns]
    if miss:
        raise KeyError(f"ไม่เจอคอลัมน์ OHLC ครบถ้วน: missing={miss}")

    out = (
        out[["date","open","high","low","close"]]
        .sort_values("date")
        .dropna(subset=["date","open","high","low","close"])
        .reset_index(drop=True)
    )
    return out

def resample_ohlc(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    tf = tf.upper()
    if tf == "1D":
        return df.copy()

    rule = {"4H":"4H","1H":"1H"}[tf]
    x = df.set_index("date")
    if len(x.index) < 3:
        return pd.DataFrame(columns=df.columns)

    # ถ้าข้อมูลไม่ละเอียดพอ (step > 1H) ให้ข้าม
    min_step = (x.index[1:] - x.index[:-1]).min() if len(x.index) > 1 else pd.Timedelta(days=9999)
    if min_step > pd.Timedelta(hours=1) and tf in {"4H","1H"}:
        return pd.DataFrame(columns=df.columns)

    y = (
        x.resample(rule)
         .agg({"open":"first","high":"max","low":"min","close":"last"})
         .dropna()
         .reset_index()
    )
    return y

def slice_with_context(df, start, end, tf: str):
    before_days = {"1D":60, "4H":45, "1H":30}.get(tf, 30)
    after_days  = {"1D":60, "4H":30, "1H":21}.get(tf, 21)
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end)
    s = start - pd.Timedelta(days=before_days)
    e = end   + pd.Timedelta(days=after_days)
    return df[(df["date"]>=s)&(df["date"]<=e)].copy()

# -------------------- Run tests --------------------
df_all = load_df("app/data/historical.xlsx")
df_all = normalize_df(df_all)

results = []
for tf in TF_LIST:
    base_df = df_all if tf == "1D" else resample_ohlc(df_all, tf)
    if base_df.empty:
        print(f"⚠️ ข้าม TF={tf} (resample ไม่ได้/ข้อมูลไม่พอ)")
        continue

    for label, start, end, expected in TEST_CASES:
        df_ctx = slice_with_context(base_df, start, end, tf)
        if df_ctx.empty:
            print(f"⚠️ {label} / TF={tf} ไม่มีข้อมูลพอ (รวม context)")
            continue

        det = logic_classify(df_ctx)            # ← ใช้สมองจริง
        detected_kind = det.get("kind", "UNKNOWN")

        ok = detected_kind == expected
        result = "✅ Correct" if ok else "❌ Incorrect"

        results.append({
            "period": label,
            "expected_kind": expected,
            "detected_kind": detected_kind,
            "detected_raw": det,
            "meta": {"timeframe": tf, "candles": len(df_ctx)},
            "result": result,
        })

        print("== Elliott Wave Test ==")
        print(f"TF            : {tf}")
        print(f"Period        : {label}")
        print(f"Expected Kind : {expected}")
        print(f"Detected Kind : {detected_kind}")
        print(f"Result        : {result}")
        print(f"Meta          : TF={tf}  candles={len(df_ctx)}")
        print("-"*60)

# Save logs
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"
with open(log_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4, ensure_ascii=False)
print(f"✅ Saved all results to {log_file}")
