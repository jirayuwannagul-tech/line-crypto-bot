import sys, os, json
import pandas as pd
from datetime import timedelta

# ============================================================
# [Layer 1] ให้ Python เห็น root project
# ============================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.analysis import elliott as ew

# ============================================================
# [Layer 2] ตั้งค่า Test Cases (แก้ไขแค่ตรงนี้ก็พอ)
# ============================================================
TEST_CASES = [
    ("May 2021", "2021-05-01", "2021-05-31", "IMPULSE_TOP"),
    ("Nov 2021", "2021-11-01", "2021-11-30", "IMPULSE_TOP"),
    ("Jun 2022", "2022-06-01", "2022-06-30", "CORRECTION"),
    ("Aug 2022", "2022-08-01", "2022-08-31", "CORRECTION"),
]

# พารามิเตอร์ analyzer
USE_WEEKLY = False
MIN_SWING_PCT_DAILY  = 3.5
MIN_SWING_PCT_WEEKLY = 6.0
STRICT_IMPULSE = True
ALLOW_OVERLAP  = False
CTX_DAYS_BEFORE = 60
CTX_DAYS_AFTER  = 60

# ============================================================
# [Layer 3] Helpers
# ============================================================
DATE_CANDIDATES = ["date","Date","timestamp","Timestamp","time","Time","open_time","Open time","Datetime","datetime"]
OHLC_MAPS = [
    {"Open":"open","High":"high","Low":"low","Close":"close"},
    {"open":"open","high":"high","low":"low","close":"close"},
    {"OPEN":"open","HIGH":"high","LOW":"low","CLOSE":"close"},
]

def load_df(path: str) -> pd.DataFrame:
    obj = pd.read_excel(path, sheet_name=None)
    if isinstance(obj, dict):
        first = list(obj)[0]
        df = obj[first]
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
                date_col = lower[cand]
                break
    if not date_col:
        raise KeyError(f"ไม่พบคอลัมน์วันที่ใน {cols}")

    out = df.rename(columns={date_col:"date"}).copy()
    out["date"] = pd.to_datetime(out["date"])

    for m in OHLC_MAPS:
        if len([k for k in m if k in out.columns]) >= 3:
            out = out.rename(columns=m)

    if "close" not in out.columns and "Adj Close" in out.columns:
        out = out.rename(columns={"Adj Close":"close"})

    core = ["date","open","high","low","close"]
    return out[core+[c for c in out.columns if c not in core]]

def slice_with_context(df, start, end, ctx_before, ctx_after):
    s = pd.to_datetime(start) - timedelta(days=ctx_before)
    e = pd.to_datetime(end)   + timedelta(days=ctx_after)
    return df[(df["date"]>=s)&(df["date"]<=e)].copy()

def run_analyzer(df_test, min_swing_pct, strict_impulse, allow_overlap):
    try:
        return ew.analyze_elliott(df_test,
            min_swing_pct=min_swing_pct,
            strict_impulse=strict_impulse,
            allow_overlap=allow_overlap)
    except TypeError:
        return ew.analyze_elliott(df_test)

def extract_detected(waves):
    if isinstance(waves, dict): return waves
    if isinstance(waves, list) and len(waves)>0:
        last = waves[-1]
        return last if isinstance(last, dict) else {"label": str(last)}
    return {"label": str(waves) if waves is not None else "None"}

# ============================================================
# [Layer 4] โหลดข้อมูล
# ============================================================
df_all = load_df("app/data/historical.xlsx")
df_all = normalize_df(df_all)

# ============================================================
# [Layer 5] รันทดสอบทีละ case
# ============================================================
results = []
for label, start, end, expected_kind in TEST_CASES:
    used_tf = "D" if not USE_WEEKLY else "W"
    base_df = df_all if used_tf=="D" else (
        df_all.set_index("date").resample("W")
             .agg({"open":"first","high":"max","low":"min","close":"last"})
             .dropna().reset_index()
    )
    df_ctx = slice_with_context(base_df, start, end, CTX_DAYS_BEFORE, CTX_DAYS_AFTER)

    if df_ctx.empty:
        print(f"⚠️ {label} ไม่มีข้อมูล")
        continue

    min_swing = MIN_SWING_PCT_DAILY if used_tf=="D" else MIN_SWING_PCT_WEEKLY
    waves_raw = run_analyzer(df_ctx, min_swing, STRICT_IMPULSE, ALLOW_OVERLAP)
    det = extract_detected(waves_raw)

    # classify
    pattern = str(det.get("pattern","")).upper()
    stage   = str(det.get("current",{}).get("stage","")).upper()
    nextdir = str(det.get("next",{}).get("direction","")).lower()
    completed = bool(det.get("completed", False))

    if "IMPULSE" in pattern or "IMPULSE" in stage or "W5" in stage:
        if completed or "TOP" in stage or nextdir=="down":
            detected_kind = "IMPULSE_TOP"
        else:
            detected_kind = "IMPULSE_PROGRESS"
    elif "CORRECTION" in stage or "WXY" in stage or pattern in {"DOUBLE_THREE","ZIGZAG","FLAT"}:
        detected_kind = "CORRECTION"
    else:
        detected_kind = "UNKNOWN"

    result = "✅ Correct" if detected_kind==expected_kind else "❌ Incorrect"
    summary = {
        "period": label,
        "expected_kind": expected_kind,
        "detected_kind": detected_kind,
        "detected_raw": det,
        "meta": {"timeframe":used_tf,"candles":len(df_ctx),"min_swing_pct":min_swing},
        "result": result
    }
    results.append(summary)

    print("== Elliott Wave Test ==")
    print(f"Period        : {label}")
    print(f"Expected Kind : {expected_kind}")
    print(f"Detected Kind : {detected_kind}")
    print(f"Result        : {result}")
    print(f"Meta          : TF={used_tf}  candles={len(df_ctx)}  minSwing={min_swing}%")
    print("-"*60)

# ============================================================
# [Layer 6] Save logs
# ============================================================
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"
if os.path.exists(log_file):
    with open(log_file,"r",encoding="utf-8") as f: logs=json.load(f)
else:
    logs=[]
logs.extend(results)
with open(log_file,"w",encoding="utf-8") as f:
    json.dump(logs,f,indent=4,ensure_ascii=False)

print(f"✅ Saved all results to {log_file}")
