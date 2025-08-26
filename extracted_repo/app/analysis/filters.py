# app/analysis/filters.py
# =============================================================================
# LAYER A) OVERVIEW & TYPES
# -----------------------------------------------------------------------------
# อธิบาย:
# - รวม "ตัวกรอง" หลักที่ใช้คัดสัญญาณก่อนเข้าตลาด
# - รองรับค่า threshold จากโปรไฟล์ (cholak/chinchot/baseline) แต่ยังคงใช้ได้
#   แม้ไม่มีไฟล์ YAML (มีค่า default ในโค้ด)
# - รักษา compatibility:
#     trend_filter(series, min_strength=0.0) -> bool
#     volatility_filter(series, min_atr_pct=0.005) -> bool
#     session_filter(ts_ms, allowed="24/7") -> bool
#     volume_filter(series, min_multiple_of_avg=1.0, lookback=20) -> bool
# - เพิ่ม helper: evaluate_filters(series, cfg=None) -> dict  (ไม่บังคับใช้)
# - เพิ่มฟังก์ชันระบุภาวะ SIDEWAY และคะแนนความมั่นใจ:
#     is_sideway_df(df, ...) -> pd.Series[bool]
#     side_confidence(row, ...) -> 0..100
# =============================================================================

from __future__ import annotations
from typing import Optional, Dict, Any, List, Literal, Tuple

import math

# ---- พยายามไม่ผูกกับสคีมาภายนอกแรง ๆ เพื่อให้ไฟล์นี้พกไปใช้ที่อื่นได้ง่าย ----
try:
    from app.schemas.series import Series  # {symbol,timeframe,candles:[{open,high,low,close,volume,ts}]}
except Exception:  # fallback type (สำหรับ dev/test)
    from typing import TypedDict
    class Candle(TypedDict, total=False):
        open: float; high: float; low: float; close: float; volume: float; ts: int
    class Series(TypedDict):
        symbol: str
        timeframe: str
        candles: List[Candle]

# =============================================================================
# LAYER B) LOW-LEVEL UTILS
# -----------------------------------------------------------------------------
# อธิบาย: ฟังก์ชัน utility สำหรับแปลงข้อมูล, คำนวณ EMA/ATR% ฯลฯ
# =============================================================================

def _to_df(series: Series):
    import pandas as pd
    df = pd.DataFrame(series.get("candles", []))
    # ให้แน่ใจว่าเป็นตัวเลขและเรียงตามเวลา
    for c in ("open","high","low","close","volume"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    if "ts" in df.columns:
        df = df.sort_values("ts")
        df = df.set_index("ts", drop=False)  # เก็บ ts ไว้เป็น index เพื่อ join ภายนอกได้สะดวก
    return df.dropna(subset=["open","high","low","close"])

def _ema(s, n: int):
    import pandas as pd
    s = pd.to_numeric(s, errors="coerce")
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

def _atr_pct(df, n: int = 14) -> Optional[float]:
    """คำนวณ ATR เป็นสัดส่วนของราคาปิดล่าสุด (ATR%); ถ้าข้อมูลไม่พอ คืน None"""
    import pandas as pd
    if len(df) < n + 1:
        return None
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    last_close = float(c.iloc[-1])
    if last_close == 0 or math.isnan(last_close):
        return None
    return float(atr.iloc[-1] / last_close)

def _vol_ma_and_ratio(df, lookback: int = 20) -> Tuple[Optional[float], Optional[float]]:
    """คืน (vol_ma, last_over_ma_ratio) เช่น 1.2 หมายถึงแท่งล่าสุดมากกว่าเฉลี่ย 20 แท่ง 20%"""
    import pandas as pd
    if len(df) < lookback + 1:
        return None, None
    v = pd.to_numeric(df["volume"], errors="coerce")
    ma = v.rolling(lookback, min_periods=lookback).mean().iloc[-1]
    last = float(v.iloc[-1])
    if ma is None or math.isnan(ma) or ma == 0:
        return None, None
    return float(ma), float(last / ma)

# --- เพิ่ม utils สำหรับ sideway detection ---
def _roc_pct(df, window: int = 14):
    """Return Series ของ %การเปลี่ยนแปลงเทียบ N แท่งก่อนหน้า"""
    return df["close"].pct_change(window) * 100.0

def _atr_pct_series(df, n: int = 14):
    """Return Series ATR% (ใช้กับ is_sideway_df)"""
    import pandas as pd
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    atr_pct = (atr / c) * 100.0
    return atr_pct

# =============================================================================
# LAYER C) CORE FILTERS (BACKWARD-COMPATIBLE API)
# -----------------------------------------------------------------------------
# อธิบาย:
# - ฟิลเตอร์เหล่านี้คืนค่า bool เพื่อบอกว่า "ผ่าน/ไม่ผ่าน"
# - parameter ค่า default ตั้งให้ปลอดภัย และรับ cfg (dict) เสริมได้โดยไม่บังคับ
# =============================================================================

def trend_filter(series: Series, min_strength: float = 0.0, *, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    โครงสร้างเทรนด์แบบง่าย:
      - Bull: close > EMA200 และ EMA50 > EMA200
      - Bear: close < EMA200 และ EMA50 < EMA200
    คืน True ถ้าตลาดมีทิศชัดเจน (bull หรือ bear)
    """
    cfg = cfg or {}
    df = _to_df(series)
    if len(df) < 200:  # ต้องมีอย่างน้อย 200 แท่งเพื่อความน่าเชื่อถือของ EMA200
        return False
    ema50 = _ema(df["close"], int(cfg.get("ema_mid", 50))).iloc[-1]
    ema200 = _ema(df["close"], int(cfg.get("ema_slow", 200))).iloc[-1]
    last = float(df["close"].iloc[-1])

    if any(map(lambda x: x is None or math.isnan(x), (ema50, ema200, last))):
        return False

    bull = last > ema200 and ema50 > ema200
    bear = last < ema200 and ema50 < ema200

    # min_strength เผื่ออนาคตอยากแปลงเป็นคะแนน; ตอนนี้ยังไม่ใช้ (คงไว้เพื่อ compatibility)
    return bool(bull or bear)

def volatility_filter(series: Series, min_atr_pct: float = 0.005, *, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    ตรวจสภาพคล่องของราคา (ความผันผวน) ด้วย ATR%:
      - ค่าเริ่มต้น 0.5% (0.005) หมายถึง ATR ล่าสุด >= 0.5% ของราคาปิดล่าสุด
      - ปรับได้จาก cfg["atr_min_pct"]
    """
    cfg = cfg or {}
    df = _to_df(series)
    atr_required = float(cfg.get("atr_min_pct", min_atr_pct))
    atrp = _atr_pct(df, n=int(cfg.get("atr_period", 14)))
    if atrp is None:
        return False
    return atrp >= atr_required

def session_filter(ts_ms: Optional[int], allowed: Literal["asia","eu","us","24/7"] = "24/7", *, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    MVP: คริปโตอนุญาต 24/7 ไปก่อน
    (โครงพร้อมรองรับตลาดหุ้นในอนาคตโดยดูโซนเวลา/วันทำการ)
    """
    return allowed == "24/7"

def volume_filter(series: Series, min_multiple_of_avg: float = 1.0, lookback: int = 20, *, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    วอลุ่มแท่งล่าสุด >= avg(lookback) * k
      - เริ่มต้น k=1.0 เท่ากับไม่น้อยกว่าค่าเฉลี่ย 20 แท่ง
    """
    cfg = cfg or {}
    df = _to_df(series)
    lb = int(cfg.get("vol_lookback", lookback))
    k = float(cfg.get("vol_min_multiple", min_multiple_of_avg))
    vol_ma, ratio = _vol_ma_and_ratio(df, lookback=lb)
    if vol_ma is None or ratio is None:
        return False
    return ratio >= k

# =============================================================================
# LAYER C2) SIDEWAY DETECTION & CONFIDENCE (ใหม่)
# -----------------------------------------------------------------------------
# อธิบาย:
# - เกณฑ์ SIDEWAY มาจากการผสาน ADX/ATR%/ROC%
# - ใช้ค่านิยมเริ่มต้นที่ค่อนข้าง “ผ่อน” เพื่อหลุดจากการติด SIDE ตลอด
# - สามารถ override ค่าพวกนี้ผ่าน cfg ฝั่ง strategies ได้
# =============================================================================

def is_sideway_df(
    df,
    *,
    adx_col: str = "ADX14",
    atr_period: int = 14,
    roc_window: int = 14,
    adx_thresh: float = 14.0,
    atrpct_thresh: float = 1.2,   # ATR% < 1.2% ถือว่านิ่ง
    roc_thresh: float = 1.0,      # ROC14 |%| < 1.0%
):
    """
    คืนค่า Series[bool] ว่าแท่งนั้นๆ เป็นภาวะ SIDEWAY หรือไม่
    เกณฑ์: ADX ต่ำ, ATR% ต่ำ, ROC% แคบ (AND)
    หมายเหตุ: ถ้าไม่มีคอลัมน์ ADX14/EMA20/ฯลฯ ให้เงื่อนไขนั้นไม่ผ่านโดยอัตโนมัติ (ลด false-sideway)
    """
    import pandas as pd
    # ADX เงื่อนไข
    if adx_col in df.columns:
        adx_ok = df[adx_col] < adx_thresh
    else:
        adx_ok = pd.Series(False, index=df.index)

    # ATR% เงื่อนไข
    atr_pct_ser = _atr_pct_series(df, n=atr_period)
    atr_ok = atr_pct_ser < atrpct_thresh

    # ROC เงื่อนไข
    roc = _roc_pct(df, window=roc_window)
    roc_ok = roc.abs() < roc_thresh

    side = adx_ok & atr_ok & roc_ok
    return side

def side_confidence(row, *, adx_thresh=14.0, atrpct_thresh=1.2, roc_thresh=1.0, atr_col="ATR14"):
    """
    ให้คะแนนความมั่นใจว่า 'SIDE' มากน้อยแค่ไหน (0–100)
    ใช้จำนวนเงื่อนไขที่เข้าเกณฑ์มา map เป็นสเกลง่ายๆ
    """
    cnt = 0
    # ADX
    if "ADX14" in row and row["ADX14"] is not None and not math.isnan(row["ADX14"]):
        if row["ADX14"] < adx_thresh:
            cnt += 1
    # ATR%
    atr = row.get(atr_col, None)
    if atr is not None and "close" in row and row["close"]:
        atr_pct = (atr / row["close"]) * 100.0
        if atr_pct < atrpct_thresh:
            cnt += 1
    # ROC14 (ถ้าไม่มี ใช้การเบี่ยงเบนจาก EMA20 แทน)
    roc_ok = False
    if "ROC14" in row and row["ROC14"] is not None and not math.isnan(row["ROC14"]):
        roc_ok = abs(row["ROC14"]) < roc_thresh
    elif "EMA20" in row and "close" in row and row["EMA20"] and row["close"]:
        dev = abs((row["close"] - row["EMA20"]) / row["close"] * 100.0)
        roc_ok = dev < roc_thresh
    if roc_ok:
        cnt += 1

    # map เป็นสเกล
    return {0: 15, 1: 40, 2: 65, 3: 85}.get(cnt, 30)

# =============================================================================
# LAYER D) HIGH-LEVEL AGGREGATION (OPTIONAL)
# -----------------------------------------------------------------------------
# อธิบาย:
# - ฟังก์ชันช่วยรวมผลฟิลเตอร์ทั้งหมด พร้อมเหตุผลและตัวเลขประกอบ
# - ใช้ใน scenarios/entry_exit ได้ เพื่อบันทึกเหตุผลลง log หรือรายงาน
# - ไม่บังคับใช้กับโค้ดเดิม (ของเดิมเรียกฟิลเตอร์รายตัวต่อไปได้)
# =============================================================================

def evaluate_filters(series: Series, *, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    รวมผลฟิลเตอร์ → dict:
      {
        "trend": {"pass": bool, "ema50": float, "ema200": float, "close": float},
        "volatility": {"pass": bool, "atr_pct": float, "threshold": float},
        "volume": {"pass": bool, "ratio": float, "threshold": float, "lookback": int},
        "session": {"pass": bool, "allowed": "24/7"},
        "sideway": {"mask": List[bool], "params": {...}},
        "all_pass": bool
      }
    """
    cfg = cfg or {}
    out: Dict[str, Any] = {}

    # เตรียม DataFrame เดียว ใช้ซ้ำ
    df = _to_df(series)

    # --- Trend
    trend_pass = False
    ema50 = ema200 = last = float("nan")
    if len(df) >= 200:
        ema50 = float(_ema(df["close"], int(cfg.get("ema_mid", 50))).iloc[-1])
        ema200 = float(_ema(df["close"], int(cfg.get("ema_slow", 200))).iloc[-1])
        last = float(df["close"].iloc[-1])
        if not any(map(math.isnan, (ema50, ema200, last))):
            trend_pass = (last > ema200 and ema50 > ema200) or (last < ema200 and ema50 < ema200)
    out["trend"] = {"pass": trend_pass, "ema50": ema50, "ema200": ema200, "close": last}

    # --- Volatility (ATR%)
    atr_required = float(cfg.get("atr_min_pct", 0.005))
    atrp = _atr_pct(df, n=int(cfg.get("atr_period", 14)))
    vol_pass = bool(atrp is not None and atrp >= atr_required)
    out["volatility"] = {"pass": vol_pass, "atr_pct": float(atrp) if atrp is not None else None, "threshold": atr_required}

    # --- Volume strength
    lb = int(cfg.get("vol_lookback", 20))
    k = float(cfg.get("vol_min_multiple", 1.0))
    vol_ma, ratio = _vol_ma_and_ratio(df, lookback=lb)
    volm_pass = bool(vol_ma is not None and ratio is not None and ratio >= k)
    out["volume"] = {"pass": volm_pass, "ratio": float(ratio) if ratio is not None else None, "threshold": k, "lookback": lb}

    # --- Session (คริปโต: ผ่านเสมอในโหมด 24/7)
    sess_allowed = cfg.get("session_allowed", "24/7")
    sess_pass = (sess_allowed == "24/7")
    out["session"] = {"pass": sess_pass, "allowed": sess_allowed}

    # --- Sideway mask (สำหรับ debug/report)
    adx_thresh = float(cfg.get("side_adx_thresh", 14.0))
    atrpct_thresh = float(cfg.get("side_atr_pct_thresh", 1.2))
    roc_thresh = float(cfg.get("side_roc_thresh", 1.0))
    atr_period = int(cfg.get("side_atr_period", 14))
    roc_window = int(cfg.get("side_roc_window", 14))
    mask = is_sideway_df(
        df,
        adx_col=cfg.get("side_adx_col", "ADX14"),
        atr_period=atr_period,
        roc_window=roc_window,
        adx_thresh=adx_thresh,
        atrpct_thresh=atrpct_thresh,
        roc_thresh=roc_thresh,
    )
    out["sideway"] = {
        "mask": mask.tolist(),
        "params": {
            "adx_thresh": adx_thresh,
            "atr_pct_thresh": atrpct_thresh,
            "roc_thresh": roc_thresh,
            "atr_period": atr_period,
            "roc_window": roc_window,
        }
    }

    # --- สรุป
    out["all_pass"] = bool(trend_pass and vol_pass and sess_pass)  # volume เป็นตัวเลือก จะไม่นับก็ได้
    return out
