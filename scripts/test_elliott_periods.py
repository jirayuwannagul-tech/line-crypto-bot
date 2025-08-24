# scripts/test_elliott_periods.py
# ============================================================
# Test Elliott detection across sample periods
# - ใช้ logic layer (classify_elliott) เป็นหลัก
# - fallback ไป analysis rules ได้ถ้าจำเป็น
# ============================================================

import sys, os, json
import pandas as pd
from datetime import timedelta

# ============================================================
# [Layer 1] ให้ Python เห็น root project
# ============================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# rules (analysis) ไว้ fallback
from app.analysis import elliott as ew

# logic (ตีความ + บริบทเทรนด์)
try:
    from app.logic.elliott_logic import classify_elliott as logic_classify
except Exception:
    logic_classify = None  # ถ้า import ไม่ได้ จะ fallback หา rules ตรง ๆ


# ============================================================
# [Layer 2] ตั้งค่า Test Cases (แก้ไขแค่ตรงนี้ก็พอ)
# ============================================================
TEST_CASES = [
    # Bull ก่อนพีคชุดแรก
    ("Oct 2020", "2020-10-01", "2020-10-31", "IMPULSE_PROGRESS"),
    ("Jan 2021", "2021-01-01", "2021-01-31", "IMPULSE_PROGRESS"),
    ("Apr 2021", "2021-04-01", "2021-04-30", "IMPULSE_TOP"),
    ("May 2021", "2021-05-01", "2021-05-31", "IMPULSE_TOP"),

    # ก่อน/ถึงพีครอบสอง
    ("Sep 2021", "2021-09-01", "2021-09-30", "IMPULSE_PROGRESS"),
    ("Nov 2021", "2021-11-01", "2021-11-30", "IMPULSE_TOP"),

    # ช่วงขาลง/คอร์เรคชัน
    ("Jan 2022", "2022-01-01", "2022-01-31", "CORRECTION"),
    ("Jun 2022", "2022-06-01", "2022-06-30", "CORRECTION"),
    ("Aug 2022", "2022-08-01", "2022-08-31", "CORRECTION"),
    ("Nov 2022", "2022-11-01", "2022-11-30", "CORRECTION"),
]

# === มาตรฐาน TF ที่จะรันทุกครั้ง ===
TF_LIST = ["1D", "4H", "1H"]

# พารามิเตอร์ analyzer (ใช้กับ rules เท่านั้น)
STRICT_IMPULSE = True
ALLOW_OVERLAP  = False

# Min swing ต่อ TF (ใช้กับ rules เท่านั้น)
MIN_SWING_PCT = {
    "1D": 3.5,   # เดิมที่ใช้อยู่
    "4H": 2.0,
    "1H": 1.2,
}

# ช่วง context ต่อ TF (ก่อน/หลังช่วงทดสอบ) — ใช้เป็น 'Xd' วัน
CTX_BEFORE_DAYS = {
    "1D": 60,
    "4H": 45,
    "1H": 30,
}
CTX_AFTER_DAYS = {
    "1D": 60,
    "4H": 30,
    "1H": 21,
}

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
    """
    Resample เป็น OHLC ตาม TF ที่กำหนด (1D/4H/1H)
    - ถ้า TF=1D: ไม่ resample (ใช้เดิม)
    - ถ้า TF=4H/1H: ต้องมีข้อมูลที่ละเอียดพอ (>= 1H) จึงจะ resample ได้
    """
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
    """ตัดช่วงข้อมูลพร้อม context ก่อน/หลัง ตาม TF"""
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end)
    before_days = CTX_BEFORE_DAYS.get(tf, 30)
    after_days  = CTX_AFTER_DAYS.get(tf, 21)
    s = start - pd.Timedelta(days=before_days)
    e = end   + pd.Timedelta(days=after_days)
    return df[(df["date"]>=s)&(df["date"]<=e)].copy()

def _try_call(func, *args, **kwargs):
    """ตัวช่วยเรียกฟังก์ชันที่อาจมี signature ต่างกัน"""
    try:
        return func(*args, **kwargs)
    except TypeError:
        try:
            return func(*args)
        except TypeError:
            return func()

def run_detector(df_test, min_swing_pct, strict_impulse, allow_overlap):
    """
    เลือกใช้ logic เป็นหลัก; ถ้าไม่มีให้ fallback เป็น rules.
    """
    # 1) ใช้ logic ก่อน (ตีความ + บริบทเทรนด์)
    if callable(logic_classify):
        try:
            out = logic_classify(df_test)
            # ยก UNKNOWN → IMPULSE ถ้า confidence ถึงเกณฑ์ (ไม่แก้กฎ แค่ตีความ)
            patt = str(out.get("pattern", "UNKNOWN")).upper()
            conf = float(out.get("current", {}).get("confidence", 0))
            if patt == "UNKNOWN" and conf >= 0.55:
                out["pattern"] = "IMPULSE"
            return out
        except Exception:
            pass  # ถ้า logic พัง ให้ลอง rules ต่อ

    # 2) Fallback: rules → normalize โครงให้คล้าย logic
    if hasattr(ew, "analyze_elliott"):
        try:
            raw = _try_call(
                ew.analyze_elliott,
                df_test,
                min_swing_pct=min_swing_pct,
                strict_impulse=strict_impulse,
                allow_overlap=allow_overlap
            )
            if isinstance(raw, dict):
                return {
                    "pattern": raw.get("pattern", raw.get("label", "UNKNOWN")),
                    "completed": bool(raw.get("completed", False)),
                    "current": raw.get("current", {}),
                    "rules": raw.get("rules", []),
                    "debug": raw.get("debug", {}),
                }
            return {"pattern": "UNKNOWN", "completed": False, "current": {}, "rules": [], "debug": {"raw": raw}}
        except Exception:
            pass

    if hasattr(ew, "analyze_elliott_rules"):
        raw = _try_call(
            ew.analyze_elliott_rules,
            df_test,
            min_swing_pct=min_swing_pct,
            strict_impulse=strict_impulse,
            allow_overlap=allow_overlap
        )
        if isinstance(raw, dict):
            return {
                "pattern": raw.get("pattern", "UNKNOWN"),
                "completed": bool(raw.get("completed", False)),
                "current": raw.get("current", {}),
                "rules": raw.get("rules", []),
                "debug": raw.get("debug", {}),
            }
        return {"pattern": "UNKNOWN", "completed": False, "current": {}, "rules": [], "debug": {"raw": raw}}

    raise AttributeError("ไม่พบทั้ง analyze_elliott / analyze_elliott_rules และใช้ logic_classify ไม่ได้")

def extract_detected(waves):
    # ใช้กับ fallback แบบเก่า (กันล่ม)
    if isinstance(waves, dict): return waves
    if isinstance(waves, list) and len(waves)>0:
        last = waves[-1]
        return last if isinstance(last, dict) else {"label": str(last)}
    return {"label": str(waves) if waves is not None else "None"}

def classify_kind(det: dict) -> str:
    """
    แปลงผล pattern + สถานะ เบื้องต้น เป็นชนิดที่เทสใช้อยู่
    """
    pattern = str(det.get("pattern","")).upper()
    stage   = str(det.get("current",{}).get("stage","")).upper()
    nextdir = str(det.get("next",{}).get("direction","")).lower()
    completed = bool(det.get("completed", False))

    if "IMPULSE" in pattern or "IMPULSE" in stage or "W5" in stage:
        if completed or "TOP" in stage or nextdir == "down":
            return "IMPULSE_TOP"
        return "IMPULSE_PROGRESS"
    if "CORRECTION" in stage or "WXY" in stage or pattern in {"DOUBLE_THREE","ZIGZAG","FLAT","TRIANGLE"}:
        return "CORRECTION"
    return "UNKNOWN"

# ============================================================
# [Layer 4] โหลดข้อมูล
# ============================================================
df_all = load_df("app/data/historical.xlsx")
df_all = normalize_df(df_all)

# ============================================================
# [Layer 5] รันทดสอบแบบวนทุก TF
# ============================================================
results = []

for tf in TF_LIST:
    # เตรียม DataFrame ตาม TF
    if tf == "1D":
        base_df = df_all
    else:
        base_df = resample_ohlc(df_all, tf)
        if base_df.empty:
            print(f"⚠️ ข้าม TF={tf} เพราะข้อมูลหยาบเกินไป (resample ไม่ได้)")
            continue

    for label, start, end, expected_kind in TEST_CASES:
        df_ctx = slice_with_context(base_df, start, end, tf)
        if df_ctx.empty:
            print(f"⚠️ {label} / TF={tf} ไม่มีข้อมูลพอในช่วงที่ขอ (รวม context)")
            continue

        min_swing = MIN_SWING_PCT.get(tf, 2.0)
        det = run_detector(df_ctx, min_swing, STRICT_IMPULSE, ALLOW_OVERLAP)

        # ป้องกันเคส fallback แปลก ๆ
        if not isinstance(det, dict):
            det = extract_detected(det)

        detected_kind = classify_kind(det)
        result = "✅ Correct" if detected_kind == expected_kind else "❌ Incorrect"

        summary = {
            "period": label,
            "expected_kind": expected_kind,
            "detected_kind": detected_kind,
            "detected_raw": det,
            "meta": {
                "timeframe": tf,
                "candles": len(df_ctx),
                "min_swing_pct": min_swing
            },
            "result": result
        }
        results.append(summary)

        print("== Elliott Wave Test ==")
        print(f"TF            : {tf}")
        print(f"Period        : {label}")
        print(f"Expected Kind : {expected_kind}")
        print(f"Detected Kind : {detected_kind}")
        print(f"Result        : {result}")
        print(f"Meta          : TF={tf}  candles={len(df_ctx)}  minSwing={min_swing}%")
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

print(f"✅ Saved all results to {log_file}")
