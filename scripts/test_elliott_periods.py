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
#   - ปรับช่วงเวลา / expected ที่นี่
#   - ถ้าข้อมูลน้อย analyzer อาจ "no_swings" → มี fallback อัตโนมัติ
# ============================================================
TEST_CASE = ("May 2021", "2021-05-01", "2021-05-31", "wave 5 end")

# โหมดและพารามิเตอร์เริ่มต้น
USE_WEEKLY = True          # เริ่มจากรีแซมเปิลรายสัปดาห์
MIN_SWING_PCT = 3.0        # ลดความเข้มงวดเริ่มต้น (เดิม 5.0)
STRICT_IMPULSE = True
ALLOW_OVERLAP = False
AUTO_FALLBACK_TO_DAILY = True   # ถ้า weekly ใช้ไม่ได้ → กลับไปใช้ daily อัตโนมัติ

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

    # หา column วันที่
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

    # รีเนมคอลัมน์ราคาให้เป็นมาตรฐาน
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

def slice_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    mask = (df["date"] >= pd.to_datetime(start)) & (df["date"] <= pd.to_datetime(end))
    return df.loc[mask].copy()

def run_analyzer(df_test: pd.DataFrame,
                 min_swing_pct: float,
                 strict_impulse: bool,
                 allow_overlap: bool):
    """เรียก analyzer พร้อมรองรับกรณีไม่รับ kwargs"""
    try:
        return ew.analyze_elliott(
            df_test,
            min_swing_pct=min_swing_pct,
            strict_impulse=strict_impulse,
            allow_overlap=allow_overlap
        )
    except TypeError:
        return ew.analyze_elliott(df_test)

def extract_detected(waves) -> str:
    """ดึงผล (เป็น string) รองรับหลายรูปแบบ"""
    if isinstance(waves, list) and len(waves) > 0:
        last = waves[-1]
        return last["label"] if isinstance(last, dict) and "label" in last else str(last)
    elif isinstance(waves, dict):
        return waves.get("label") or str(waves)
    else:
        return str(waves) if waves is not None else "None"

def get_debug_reason(waves) -> str:
    """ดึง debug.reason ถ้ามี"""
    if isinstance(waves, dict):
        dbg = waves.get("debug") or {}
        return str(dbg.get("reason", ""))
    return ""

# ============================================================
# [Layer 3] โหลด + มาตรฐานข้อมูล
# ============================================================
df_all = load_df("app/data/historical.xlsx")
df_all = normalize_df(df_all)

# ============================================================
# [Layer 4] เลือกกรอบเวลา (weekly → daily fallback ถ้าจำเป็น)
# ============================================================
label, start, end, expected = TEST_CASE

used_timeframe = "W"
source_df = resample_weekly(df_all) if USE_WEEKLY else df_all
df_test = slice_period(source_df, start, end)

# ถ้า weekly ไม่พอแท่ง หรือว่าง → fallback daily
if df_test.empty or len(df_test) < 6:  # น้อยเกินไปสำหรับนับคลื่น
    if USE_WEEKLY and AUTO_FALLBACK_TO_DAILY:
        used_timeframe = "D"
        source_df = df_all  # รายวัน
        df_test = slice_period(source_df, start, end)

if df_test.empty:
    raise ValueError(f"ช่วง {start} → {end} ไม่มีข้อมูล (TF={used_timeframe})")

# ============================================================
# [Layer 5] วิเคราะห์ + ลอง fallback ถ้า no_swings
# ============================================================
waves = run_analyzer(df_test, MIN_SWING_PCT, STRICT_IMPULSE, ALLOW_OVERLAP)
detected = extract_detected(waves)
reason = get_debug_reason(waves)

# ถ้า weekly แล้วยัง no_swings → ลอง fallback เป็น daily อัตโนมัติ
if "no_swings" in reason and used_timeframe == "W" and AUTO_FALLBACK_TO_DAILY:
    used_timeframe = "D"
    source_df = df_all
    df_test = slice_period(source_df, start, end)
    # ลองลด min_swing_pct ลงอีกนิด
    waves = run_analyzer(df_test, max(MIN_SWING_PCT - 1.0, 2.0), STRICT_IMPULSE, ALLOW_OVERLAP)
    detected = extract_detected(waves)
    reason = get_debug_reason(waves)

# ============================================================
# [Layer 6] สรุปผล (เทียบ expected แบบ substring เดิม)
#   * ถ้าต้องการยืดหยุ่นขึ้น: เปลี่ยนกติกาเทียบชนิดโครงสร้างแทน
# ============================================================
result = "✅ Correct" if (detected and expected.lower() in str(detected).lower()) else "❌ Incorrect"

summary = {
    "period": label,
    "expected": expected,
    "detected": detected,
    "result": result,
    "meta": {
        "timeframe": used_timeframe,
        "candles": int(len(df_test)),
        "debug_reason": reason
    }
}

# ============================================================
# [Layer 7] บันทึกผลรวม (append ลงไฟล์ log)
# ============================================================
os.makedirs("app/reports/tests", exist_ok=True)
log_file = "app/reports/tests/elliott_test_log.json"
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
print("== Elliott Wave Test ==")
print(f"Period   : {label}")
print(f"Expected : {expected}")
print(f"Detected : {detected}")
print(f"Result   : {result}")
print(f"Meta     : TF={summary['meta']['timeframe']}  candles={summary['meta']['candles']}  reason={summary['meta']['debug_reason'] or '-'}")
print(f"✅ Saved to {log_file}")
