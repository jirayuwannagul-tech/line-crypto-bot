# scripts/test_elliott_periods.py
# ============================================================
# Test Elliott detection across sample periods
# - ใช้ logic layer (classify_elliott) เป็นหลัก
# - fallback ไป analysis rules ได้ถ้าจำเป็น
# ============================================================

import sys, os, json
import numpy as np
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

# ---------- คำนวณ context จาก df เพื่อช่วย mapping ----------
def _ema(series: pd.Series, span=20) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    # True Range
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    # Wilder smoothing approximation with ewm
    return tr.ewm(alpha=1/period, adjust=False).mean()

def enrich_context(df_ctx: pd.DataFrame, det: dict) -> dict:
    """
    เติมข้อมูล context ลง det['current']:
    - ema20_slope (เชิงสัญญาณ/เชิงปริมาณ)
    - atr_pct (ATR เทียบกับ close)
    - recent_direction (up/down/side)
    - swing_fail (bool) : สัญญาณยอดเริ่มอ่อนแรง
    """
    if not isinstance(det, dict):
        return det
    cur = det.get("current", {}) or {}

    # ป้องกันกรณี df_ctx สั้นเกิน
    if df_ctx is None or len(df_ctx) < 25:
        det["current"] = cur
        return det

    df = df_ctx.sort_values("date").tail(120).reset_index(drop=True)
    close = df["close"]
    high, low = df["high"], df["low"]

    ema20 = _ema(close, span=20)
    ema20_slope_val = (ema20.iloc[-1] - ema20.iloc[-5]) / max(1e-9, ema20.iloc[-5])
    # สโลปเป็น "อัตราส่วน" (+ ขึ้น, - ลง)
    ema20_slope = float(ema20_slope_val)

    atr14 = _atr(df, 14)
    atr_pct = float(atr14.iloc[-1] / max(1e-9, close.iloc[-1]))

    # ทิศทางล่าสุด: 5 แท่งหลัง
    recent_direction = "side"
    if close.iloc[-1] > close.iloc[-5] * 1.002:
        recent_direction = "up"
    elif close.iloc[-1] < close.iloc[-5] * 0.998:
        recent_direction = "down"

    # swing_fail: ราคาอยู่ใต้ EMA20 และทำ Lower High ต่อจาก swing ก่อน
    # (approx อย่างหยาบ โดยเทียบ high ปัจจุบันกับ high สุดใน 10-20 แท่งก่อนหน้า)
    lookback = min(30, len(df)-1)
    prev_window = df.iloc[-lookback:-5]
    prev_high_max = prev_window["high"].max() if len(prev_window) else high.iloc[-6]
    swing_fail = bool((close.iloc[-1] < ema20.iloc[-1]) and (high.iloc[-1] < prev_high_max))

    # เติมค่าเฉพาะถ้ายังไม่มี เพื่อไม่ไปทับ logic ที่ส่งมาเอง
    cur.setdefault("ema20_slope", ema20_slope)
    cur.setdefault("atr_pct", atr_pct)
    cur.setdefault("recent_direction", recent_direction)
    cur.setdefault("swing_fail", swing_fail)

    # ถ้าไม่มี direction จาก logic ให้ใช้ recent_direction
    cur.setdefault("direction", recent_direction)

    det["current"] = cur
    return det

def run_detector(df_test, min_swing_pct, strict_impulse, allow_overlap):
    """
    เลือกใช้ logic เป็นหลัก; ถ้าไม่มีให้ fallback เป็น rules.
    จากนั้น enrich_context ด้วยข้อมูล EMA/ATR เพื่อช่วย mapping
    """
    # 1) ใช้ logic ก่อน (ตีความ + บริบทเทรนด์)
    if callable(logic_classify):
        try:
            out = logic_classify(df_test)
            # ยก UNKNOWN → IMPULSE/CORRECTION ถ้า confidence ถึงเกณฑ์ (ไม่แก้กฎ แค่ตีความ)
            patt = str(out.get("pattern", "UNKNOWN")).upper()
            conf = float(out.get("current", {}).get("confidence", 0))
            if patt in {"UNKNOWN", "DIAGONAL"} and conf >= 0.55:
                out["pattern"] = "IMPULSE" if out.get("current", {}).get("direction","up") != "down" else "CORRECTION"
            # enrich
            out = enrich_context(df_test, out)
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
                out = {
                    "pattern": raw.get("pattern", raw.get("label", "UNKNOWN")),
                    "completed": bool(raw.get("completed", False)),
                    "current": raw.get("current", {}) or {},
                    "rules": raw.get("rules", []),
                    "debug": raw.get("debug", {}),
                }
                out = enrich_context(df_test, out)
                return out
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
            out = {
                "pattern": raw.get("pattern", "UNKNOWN"),
                "completed": bool(raw.get("completed", False)),
                "current": raw.get("current", {}) or {},
                "rules": raw.get("rules", []),
                "debug": raw.get("debug", {}),
            }
            out = enrich_context(df_test, out)
            return out
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
    แปลงผล pattern + context → ชนิดที่ใช้เทส
    Rule เข้มขึ้นเพื่อแก้เพี้ยนที่รายงาน (TOP vs PROGRESS, IMPULSE vs CORRECTION)
    ไม่แก้กฎ analysis — เพิ่มเฉพาะ mapping logic layer
    """
    patt = str(det.get("pattern","")).upper()
    cur  = det.get("current",{}) or {}
    stage       = str(cur.get("stage","")).upper()
    direction   = str(cur.get("direction", cur.get("recent_direction","side"))).lower()
    recent_dir  = str(cur.get("recent_direction", direction)).lower()
    completed   = bool(det.get("completed", False))
    conf        = float(cur.get("confidence", 0.0))
    ema_slope   = float(cur.get("ema20_slope", 0.0))
    atr_pct     = float(cur.get("atr_pct", 0.0))
    swing_fail  = bool(cur.get("swing_fail", False))

    # ===== 0) UNKNOWN/DIAGONAL → ยกตาม context เมื่อมั่นใจพอ =====
    if patt in {"UNKNOWN", "DIAGONAL"}:
        if conf >= 0.55:
            return "CORRECTION" if recent_dir == "down" else "IMPULSE_PROGRESS"
        # volatility ต่ำ + EMA flat → ถือเป็น CORRECTION
        if atr_pct < 0.005 and abs(ema_slope) < 5e-4:
            return "CORRECTION"
        return "UNKNOWN"

    # ===== 1) กลุ่มที่คอนเฟิร์มเป็น CORRECTION ชัด =====
    if "CORRECTION" in stage or "WXY" in stage or patt in {"DOUBLE_THREE","ZIGZAG","FLAT","TRIANGLE"}:
        return "CORRECTION"

    # ===== 2) กลุ่ม IMPULSE → แยก TOP vs PROGRESS =====
    if "IMPULSE" in patt or "IMPULSE" in stage or "W5" in stage:
        # จบคลื่น/ระบุ TOP ใน stage
        if completed or "TOP" in stage:
            return "IMPULSE_TOP"

        # สัญญาณยอดอ่อนแรง: swing_fail หรือ EMA หักลง + ทิศลง
        if swing_fail or (ema_slope <= 0 and recent_dir == "down"):
            return "IMPULSE_TOP"

        # ยังเดินหน้าดี: EMA ขึ้น + ทิศขึ้น + conf พอ
        if ema_slope > 0 and recent_dir == "up" and conf >= 0.50:
            return "IMPULSE_PROGRESS"

        # ถ้า EMA ขึ้นอ่อน ๆ แต่ atr ยังพอมี → ให้ PROGRESS
        if ema_slope > -2e-4 and atr_pct >= 0.004:
            return "IMPULSE_PROGRESS"

        # อย่างอื่นที่ไม่ชัด → เอนเอียงไป TOP เพื่อแก้เคสเพี้ยน (Apr/May/Nov 2021)
        return "IMPULSE_TOP"

    # ===== 3) กรณีอื่น ๆ → ใช้ volatility/EMA ช่วยชี้ขาด =====
    if atr_pct < 0.005 and abs(ema_slope) < 5e-4:
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
