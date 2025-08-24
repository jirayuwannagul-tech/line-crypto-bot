# scripts/test_elliott_periods.py
# ============================================================
# Test Elliott detection across sample periods
# - ใช้ logic layer (classify_elliott) เป็นหลัก
# - fallback ไป analysis rules ได้ถ้าจำเป็น
# ============================================================

import sys, os, json
import pandas as pd

# ============================================================
# [Layer 1] ให้ Python เห็น root project
# ============================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# rules (analysis) ไว้ fallback
from app.analysis import elliott as ew

# logic (ตีความ + บริบทเทรนด์)
try:
    from app.logic.elliott_logic import classify_elliott_with_kind as logic_classify
except Exception:
    logic_classify = None  # ถ้า import ไม่ได้ จะ fallback หา rules ตรง ๆ


# ============================================================
# [Layer 2] ตั้งค่า Test Cases
# ============================================================
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

MIN_SWING_PCT = {
    "1D": 3.5,
    "4H": 2.0,
    "1H": 1.2,
}

CTX_BEFORE_DAYS = {"1D": 60, "4H": 45, "1H": 30}
CTX_AFTER_DAYS = {"1D": 60, "4H": 30, "1H": 21}


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

    rule = {"4H": "4H", "1H": "1H"}[tf]
    x = df.set_index("date")
    if len(x.index) >= 3:
        min_step = (x.index[1:] - x.index[:-1]).min()
    else:
        min_step = pd.Timedelta(days=9999)

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
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end)
    s = start - pd.Timedelta(days=CTX_BEFORE_DAYS.get(tf, 30))
    e = end   + pd.Timedelta(days=CTX_AFTER_DAYS.get(tf, 21))
    return df[(df["date"]>=s)&(df["date"]<=e)].copy()

def run_detector(df_test, min_swing_pct):
    if callable(logic_classify):
        try:
            return logic_classify(df_test)
        except Exception:
            pass
    if hasattr(ew, "analyze_elliott"):
        return ew.analyze_elliott(df_test, min_swing_pct=min_swing_pct, strict_impulse=True, allow_overlap=False)
    return {"pattern":"UNKNOWN","completed":False,"current":{}}


# ============================================================
# [Layer 4] โหลดข้อมูล
# ============================================================
df_all = load_df("app/data/historical.xlsx")
df_all = normalize_df(df_all)

# ============================================================
# [Layer 5] รันทดสอบ
# ============================================================
results = []

for tf in TF_LIST:
    if tf == "1D":
        base_df = df_all
    else:
        base_df = resample_ohlc(df_all, tf)
        if base_df.empty:
            print(f"⚠️ ข้าม TF={tf} เพราะข้อมูลหยาบเกินไป")
            continue

    for label, start, end, expected_kind in TEST_CASES:
        df_ctx = slice_with_context(base_df, start, end, tf)
        if df_ctx.empty:
            print(f"⚠️ {label} / TF={tf} ไม่มีข้อมูลพอ")
            continue

        min_swing = MIN_SWING_PCT.get(tf, 2.0)
        det = run_detector(df_ctx, min_swing)

        detected_kind = det.get("kind") or det.get("pattern","UNKNOWN")
        result = "✅ Correct" if detected_kind == expected_kind else "❌ Incorrect"

        summary = {
            "period": label,
            "expected_kind": expected_kind,
            "detected_kind": detected_kind,
            "detected_raw": det,
            "meta": {"timeframe": tf, "candles": len(df_ctx)},
            "result": result
        }
        results.append(summary)

        print("== Elliott Wave Test ==")
        print(f"TF            : {tf}")
        print(f"Period        : {label}")
        print(f"Expected Kind : {expected_kind}")
        print(f"Detected Kind : {detected_kind}")
        print(f"Result        : {result}")
        print(f"Meta          : TF={tf}  candles={len(df_ctx)}")
        print("-"*60)

# ============================================================
# [Layer 6] Save logs
# ============================================================
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"
if os.path.exists(log_file):
    try:
        with open(log_file,"r",encoding="utf-8") as f:
            logs = json.load(f)
            if not isinstance(logs, list):
                logs = []
    except Exception:
        logs = []
else:
    logs = []

logs.extend(results)
with open(log_file,"w",encoding="utf-8") as f:
    json.dump(logs, f, indent=4, ensure_ascii=False)

# ============================================================
# [Layer 7] Main runner
# ============================================================
if __name__ == "__main__":
    print("🚀 Running Elliott Wave tests ...")
    for r in results:
        print(
            f"[{r['meta']['timeframe']}] {r['period']} | "
            f"Expected={r['expected_kind']} | Detected={r['detected_kind']} "
            f"=> {r['result']}"
        )
    print(f"✅ Saved all results to {log_file}")
