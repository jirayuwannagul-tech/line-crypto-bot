import sys, os, json
import pandas as pd
from datetime import timedelta

# ============================================================
# [Layer 1] ให้ Python เห็น root project
# ============================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.analysis import elliott as ew

# ============================================================
# [Layer 2] ตั้งค่า / Test Case
# ============================================================
# เป้าหมายเดิม: ตรวจว่า May 2021 เป็น "จบคลื่น 5" (IMPULSE_TOP)
TEST_CASE = ("May 2021", "2021-05-01", "2021-05-31", "IMPULSE_TOP")

# --- ปรับตามตัวเลือก B ---
USE_WEEKLY = False              # ใช้ "รายวัน" (ยกเลิกรีแซมเปิลรายสัปดาห์)
MIN_SWING_PCT_WEEKLY = 6.0      # ไม่ใช้ในโหมดนี้ แต่คงไว้เผื่อสลับกลับ
MIN_SWING_PCT_DAILY  = 3.5      # ลดความเข้มงวด เพื่อเห็นโครงสร้างมากขึ้น
STRICT_IMPULSE = True
ALLOW_OVERLAP  = False
AUTO_FALLBACK_TO_DAILY = True   # เผื่อใช้ ถ้าเปลี่ยนใจกลับไปเริ่มจาก weekly

# เพิ่มบริบทก่อน/หลังให้กว้างขึ้น
CTX_DAYS_BEFORE = 60
CTX_DAYS_AFTER  = 60

# ============================================================
# [Layer 2.1] Helpers: โหลด & มาตรฐานคอลัมน์
# ============================================================
DATE_CANDIDATES = ["date", "Date", "timestamp", "Timestamp", "time", "Time", "open_time", "Open time", "Datetime", "datetime"]
OHLC_MAPS = [
    {"Open": "open", "High": "high", "Low": "low", "Close": "close"},  # Yahoo
    {"open": "open", "high": "high", "low": "low", "close": "close"},   # lower
    {"OPEN": "open", "HIGH": "high", "LOW": "low", "CLOSE": "close"},   # upper
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
    if date_col is None:
        lower = {c.lower(): c for c in cols}
        for cand in [c.lower() for c in DATE_CANDIDATES]:
            if cand in lower:
                date_col = lower[cand]
                break
    if date_col is None:
        raise KeyError(f"ไม่พบคอลัมน์วันที่ใน {cols}")

    out = df.rename(columns={date_col: "date"}).copy()
    out["date"] = pd.to_datetime(out["date"])

    for m in OHLC_MAPS:
        hits = [k for k in m.keys() if k in out.columns]
        if len(hits) >= 3:
            out = out.rename(columns=m)

    missing = [c for c in ["open", "high", "low", "close"] if c not in out.columns]
    if missing:
        if "Adj Close" in out.columns and "close" not in out.columns:
            out = out.rename(columns={"Adj Close": "close"})
            missing = [c for c in ["open", "high", "low", "close"] if c not in out.columns]
    if missing:
        raise KeyError(f"ขาดคอลัมน์ราคา {missing} ใน {list(out.columns)}")

    core = ["date", "open", "high", "low", "close"]
    return out[core + [c for c in out.columns if c not in core]]

def resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.set_index("date")
          .resample("W")
          .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
          .dropna()
          .reset_index()
    )

def slice_with_context(df: pd.DataFrame, start: str, end: str, ctx_before: int, ctx_after: int) -> pd.DataFrame:
    s = pd.to_datetime(start) - timedelta(days=ctx_before)
    e = pd.to_datetime(end)   + timedelta(days=ctx_after)
    mask = (df["date"] >= s) & (df["date"] <= e)
    return df.loc[mask].copy()

def run_analyzer(df_test: pd.DataFrame, min_swing_pct: float, strict_impulse: bool, allow_overlap: bool):
    try:
        return ew.analyze_elliott(
            df_test,
            min_swing_pct=min_swing_pct,
            strict_impulse=strict_impulse,
            allow_overlap=allow_overlap
        )
    except TypeError:
        return ew.analyze_elliott(df_test)

def extract_detected(waves) -> dict | str:
    if isinstance(waves, dict):
        return waves
    if isinstance(waves, list) and len(waves) > 0:
        last = waves[-1]
        return last if isinstance(last, dict) else {"label": str(last)}
    return {"label": str(waves) if waves is not None else "None"}

def get_debug_reason(waves_dict: dict) -> str:
    dbg = waves_dict.get("debug") or {}
    return str(dbg.get("reason", ""))

# ============================================================
# [Layer 3] โหลด + มาตรฐานข้อมูล
# ============================================================
df_all = load_df("app/data/historical.xlsx")
df_all = normalize_df(df_all)

# ============================================================
# [Layer 4] เลือกกรอบเวลา + context (เริ่มที่รายวันตามตัวเลือก B)
# ============================================================
label, start, end, expected_kind = TEST_CASE
used_timeframe = "D"
base_df = df_all

df_ctx = slice_with_context(base_df, start, end, CTX_DAYS_BEFORE, CTX_DAYS_AFTER)
if df_ctx.empty or len(df_ctx) < 20:
    # ถ้าข้อมูลรายวันน้อยเกินไป ลองรีแซมเปิลเป็นรายสัปดาห์แทน
    used_timeframe = "W"
    base_df = resample_weekly(df_all)
    df_ctx = slice_with_context(base_df, start, end, CTX_DAYS_BEFORE, CTX_DAYS_AFTER)

if df_ctx.empty:
    raise ValueError(f"ช่วง {start} → {end} ไม่มีข้อมูล (TF={used_timeframe})")

# ============================================================
# [Layer 5] วิเคราะห์ (bias ไปทาง impulse top) + ปรับความเข้มงวด
# ============================================================
min_swing = MIN_SWING_PCT_DAILY if used_timeframe == "D" else MIN_SWING_PCT_WEEKLY
waves_raw = run_analyzer(df_ctx, min_swing, STRICT_IMPULSE, ALLOW_OVERLAP)
det = extract_detected(waves_raw)
reason = get_debug_reason(det)

# ถ้าข้อมูลยัง "no_swings" ให้ลดความเข้มงวดเล็กน้อย
if "no_swings" in reason:
    new_min = max(min_swing - 0.5, 2.5)  # ลดทีละ 0.5 แต่ไม่ต่ำกว่า 2.5
    waves_raw = run_analyzer(df_ctx, new_min, STRICT_IMPULSE, ALLOW_OVERLAP)
    det = extract_detected(waves_raw)
    reason = get_debug_reason(det)
    min_swing = new_min

# ============================================================
# [Layer 6] สรุปผลแบบ "ชนิดโครงสร้าง"
# ============================================================
CORRECTION_PATTERNS = {"DOUBLE_THREE", "TRIPLE_THREE", "ZIGZAG", "FLAT", "EXPANDED_FLAT", "WXY", "WXYXZ"}
IMPULSE_PATTERNS    = {"IMPULSE", "FIVE", "FIVE_WAVE", "IMPULSE_FIVE"}

def classify_detected(det: dict) -> str:
    pattern = str(det.get("pattern", "")).upper()
    completed = bool(det.get("completed", False))
    current = det.get("current", {}) or {}
    next_    = det.get("next", {}) or {}
    stage = str(current.get("stage", "")).upper()
    next_dir = str(next_.get("direction", "")).lower()

    if pattern in CORRECTION_PATTERNS or "WXY" in stage or "CORRECTION" in stage:
        return "CORRECTION"

    if (pattern in IMPULSE_PATTERNS or "IMPULSE" in stage or "W5" in stage) and (
        completed or "TOP" in stage or "PEAK" in stage or next_dir == "down"
    ):
        return "IMPULSE_TOP"

    if (pattern in IMPULSE_PATTERNS or "IMPULSE" in stage):
        return "IMPULSE_PROGRESS"

    return "UNKNOWN"

det_kind = classify_detected(det)
result = "✅ Correct" if det_kind == expected_kind else "❌ Incorrect"

# ============================================================
# [Layer 7] บันทึกผลรวม (append ลงไฟล์ log)
# ============================================================
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"

summary = {
    "period": label,
    "expected_kind": expected_kind,
    "detected_kind": det_kind,
    "detected_raw": det,
    "meta": {
        "timeframe": used_timeframe,
        "candles": int(len(df_ctx)),
        "min_swing_pct": min_swing,
        "debug_reason": reason or "-"
    },
    "result": result
}

if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8") as f:
        logs = json.load(f)
else:
    logs = []
logs.append(summary)
with open(log_file, "w", encoding="utf-8") as f:
    json.dump(logs, f, indent=4, ensure_ascii=False)

# ============================================================
# [Layer 8] แสดงผลบน Console
# ============================================================
print("== Elliott Wave Test (Impulse-Top mode / Daily TF) ==")
print(f"Period        : {label}")
print(f"Expected Kind : {expected_kind}")
print(f"Detected Kind : {det_kind}")
print(f"Result        : {result}")
print(f"Meta          : TF={summary['meta']['timeframe']}  candles={summary['meta']['candles']}  "
      f"minSwing={summary['meta']['min_swing_pct']}%  reason={summary['meta']['debug_reason']}")
print(f"✅ Saved to {log_file}")
