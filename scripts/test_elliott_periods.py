import sys, os, json
import pandas as pd

# ============================================================
# [Layer 1] ให้ Python เห็น root project
# ============================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.analysis import elliott as ew

# ============================================================
# [Layer 2] กำหนดเคสทดสอบ
#   รูปแบบ: (label, start_date, end_date, expected_wave_text)
# ============================================================
TEST_CASE = ("May 2021", "2021-05-01", "2021-05-31", "wave 5 end")

# ============================================================
# [Layer 2.1] Helper: โหลด + ปรับคอลัมน์
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

# ============================================================
# [Layer 3] โหลดข้อมูล + มาตรฐานคอลัมน์
# ============================================================
df = load_df("app/data/historical.xlsx")
df = normalize_df(df)

# ============================================================
# [Layer 3.5] รีแซมเปิลเป็นรายสัปดาห์ (ลด noise ให้โครงสร้างคลื่นใหญ่ชัด)
# ============================================================
df_w = (
    df.set_index("date")
      .resample("W")
      .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
      .dropna()
      .reset_index()
)

# ============================================================
# [Layer 4] กรองช่วงทดสอบ
# ============================================================
label, start, end, expected = TEST_CASE
mask = (df_w["date"] >= pd.to_datetime(start)) & (df_w["date"] <= pd.to_datetime(end))
df_test = df_w.loc[mask].copy()
if df_test.empty:
    raise ValueError(f"ช่วง {start} → {end} ไม่มีข้อมูลหลังรีแซมเปิล (ลองขยายช่วงหรือใช้ df รายวัน)")

# ============================================================
# [Layer 5] รัน Elliott Analyzer (โหมดเข้มงวด + รองรับกรณี analyzer ไม่รับ kwargs)
# ============================================================
try:
    waves = ew.analyze_elliott(
        df_test,
        min_swing_pct=5.0,     # ปรับ 3–8% ตามต้องการ
        strict_impulse=True,
        allow_overlap=False
    )
except TypeError:
    waves = ew.analyze_elliott(df_test)

# ดึงผลแบบปลอดภัย (รองรับหลายชนิดข้อมูล)
if isinstance(waves, list) and len(waves) > 0:
    last = waves[-1]
    detected = last["label"] if isinstance(last, dict) and "label" in last else str(last)
elif isinstance(waves, dict):
    detected = waves.get("label") or str(waves)
else:
    detected = str(waves) if waves is not None else "None"

# ============================================================
# [Layer 6] สรุปผล (กติกาเดิม: เทียบกับ expected string ตรง ๆ)
#   * หากต้องการให้ยืดหยุ่นขึ้น ให้เปลี่ยนเป็นเทียบ 'ชนิดโครงสร้าง'
# ============================================================
result = "✅ Correct" if (detected and expected.lower() in str(detected).lower()) else "❌ Incorrect"
summary = {
    "period": label,
    "expected": expected,
    "detected": detected,
    "result": result
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
print(f"✅ Saved to {log_file}")
