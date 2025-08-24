# scripts/test_elliott_periods_runner.py
import sys, os
import pandas as pd

# ให้ Python เห็น root project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# import logic และ fallback rules
from app.analysis import elliott as ew
try:
    from app.logic.elliott_logic import classify_elliott_with_kind as logic_classify
except Exception:
    logic_classify = None

# ============================================================
# Test Cases
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

TF = "1D"
MIN_SWING_PCT = 3.5
CTX_BEFORE = 60
CTX_AFTER = 60

DATE_CANDIDATES = ["date","Date","timestamp","Timestamp","time","Time","open_time","Open time","Datetime","datetime"]

# ============================================================
# Helpers
# ============================================================
def load_df(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)

    # หา column วันที่ที่ตรงกับ DATE_CANDIDATES
    date_col = None
    for candidate in DATE_CANDIDATES:
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None:
        raise ValueError(f"❌ ไม่พบ column วันที่ในไฟล์ {path}. ตรวจสอบชื่อ column ใน {DATE_CANDIDATES}")

    # แปลงเป็น datetime
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)

def slice_with_context(df, start, end):
    start = pd.to_datetime(start) - pd.Timedelta(days=CTX_BEFORE)
    end   = pd.to_datetime(end) + pd.Timedelta(days=CTX_AFTER)
    return df[(df["date"]>=start)&(df["date"]<=end)].copy()

def run_detector(df_test):
    if callable(logic_classify):
        try:
            return logic_classify(df_test)
        except Exception:
            pass
    if hasattr(ew, "analyze_elliott"):
        return ew.analyze_elliott(df_test, min_swing_pct=MIN_SWING_PCT, strict_impulse=True, allow_overlap=False)
    return {"pattern":"UNKNOWN","completed":False,"current":{}}

# ============================================================
# Main runner
# ============================================================
if __name__ == "__main__":
    df_all = load_df("app/data/historical.xlsx")

    print("🚀 Running Elliott Wave tests ...")
    for label, start, end, expected_kind in TEST_CASES:
        df_ctx = slice_with_context(df_all, start, end)
        if df_ctx.empty:
            print(f"⚠️ {label} ไม่มีข้อมูลพอ")
            continue

        det = run_detector(df_ctx)
        detected_kind = det.get("kind") or det.get("pattern","UNKNOWN")
        result = "✅ Correct" if detected_kind == expected_kind else "❌ Incorrect"

        print("------------------------------------------------------------")
        print(f"Period        : {label}")
        print(f"Expected Kind : {expected_kind}")
        print(f"Detected Kind : {detected_kind}")
        print(f"Result        : {result}")

    print("✅ Test run completed")
