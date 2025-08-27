from __future__ import annotations

import os
import re
import math
import time
import asyncio
from typing import Literal, Optional, Sequence, List, Tuple, Dict

import pandas as pd
import pathlib 
# ---- Public API ----
__all__ = [
    "get_data",
    "SUPPORTED_TF",
    "RequiredColumnsMissing",
    # สำหรับ worker/health (เรียกใช้เมื่อจำเป็นเท่านั้น)
    "start_timeframe_service",
    "stop_timeframe_service",
    "get_last_updated",
]

# ---- Config ----
DATA_PATH_DEFAULT = os.getenv("HISTORICAL_XLSX_PATH", "app/data/historical.xlsx")
SUPPORTED_TF: tuple[str, ...] = ("1H", "4H", "1D", "1W")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")

# ========= Real-time fetch settings (ENV) =========
REALTIME_ON = os.getenv("REALTIME", "").strip() == "1"
REALTIME_PROVIDERS = [p.strip().lower() for p in os.getenv("PROVIDERS", "binance").split(",") if p.strip()]
REALTIME_LIMIT = int(os.getenv("REALTIME_LIMIT", "1000"))      # per API call (max 1000 for Binance)
REALTIME_TIMEOUT = int(os.getenv("REALTIME_TIMEOUT", "12"))    # seconds

# ---- Background updater config (ใช้เมื่อเรียก start_timeframe_service) ----
_TIMEFRAME_SECONDS: Dict[str, int] = {
    "1H": 3600,
    "4H": 14400,
    "1D": 86400,
    "1W": 604800,
}
_BACKGROUND_WARM_LIMIT = int(os.getenv("BACKGROUND_WARM_LIMIT", "1000"))   # ดึงรอบแรก
_BACKGROUND_CYCLE_LIMIT = int(os.getenv("BACKGROUND_CYCLE_LIMIT", "300"))  # รอบถัดไป

# ---- Errors ----
class RequiredColumnsMissing(ValueError):
    """Raised when required OHLCV columns are missing in Excel/CSV sheet."""
    pass


# ---- Helpers (names) ----
def _sheet_name(symbol: str, tf: str) -> str:
    sym = symbol.upper().replace(":", "").replace("/", "")
    tf_norm = tf.upper()
    return f"{sym}_{tf_norm}"

def _normalize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


# ---- Excel helpers ----
def _resolve_sheet_name(
    xlsx_path: str,
    symbol: str,
    tf: str,
    engine: Optional[str],
) -> str:
    if not xlsx_path or not os.path.exists(xlsx_path):
        raise FileNotFoundError(f"Excel file not found: {xlsx_path}")

    symbol_u = symbol.upper().replace(":", "").replace("/", "")
    tf_u = tf.upper()

    target_variants = [
        f"{symbol_u}_{tf_u}",
        f"{symbol_u}-{tf_u}",
        f"{symbol_u} {tf_u}",
        f"{symbol_u}{tf_u}",
        f"{tf_u}_{symbol_u}",
        f"{tf_u}-{symbol_u}",
        f"{tf_u} {symbol_u}",
    ]
    target_norms = {_normalize(x) for x in target_variants}

    xls = pd.ExcelFile(xlsx_path, engine=engine)
    by_norm = {_normalize(s): s for s in xls.sheet_names}

    for t in target_norms:
        if t in by_norm:
            return by_norm[t]

    sym_n = _normalize(symbol_u)
    tf_n = _normalize(tf_u)
    for nrm, real in by_norm.items():
        if sym_n in nrm and tf_n in nrm:
            return real

    raise ValueError(
        "Worksheet not found for symbol/timeframe. "
        f"Expected something like one of: {target_variants}. "
        f"Available sheets: {xls.sheet_names}"
    )

def _ensure_required_columns(df: pd.DataFrame, where: str) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RequiredColumnsMissing(
            f"{where} missing columns: {missing}. Expected: {list(REQUIRED_COLUMNS)}"
        )
    return df.loc[:, list(REQUIRED_COLUMNS)]

def _parse_and_clean_strict(df: pd.DataFrame) -> pd.DataFrame:
    # robust timestamp parsing with unit detection (s/ms/us/ns)
    ts_raw = pd.to_numeric(df['timestamp'], errors='coerce')
    if ts_raw.notna().sum() == 0:
        # not numeric (e.g., date strings) → let pandas parse
        ts = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    else:
        m = float(ts_raw.max())
        if m < 1e12:       # seconds
            ts = pd.to_datetime(ts_raw, unit='s',  utc=True, errors='coerce')
        elif m < 1e14:     # milliseconds
            ts = pd.to_datetime(ts_raw, unit='ms', utc=True, errors='coerce')
        elif m < 1e17:     # microseconds
            ts = pd.to_datetime(ts_raw, unit='us', utc=True, errors='coerce')
        else:              # nanoseconds
            ts = pd.to_datetime(ts_raw, unit='ns', utc=True, errors='coerce')
    df = df.assign(timestamp=ts).dropna(subset=['timestamp'])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("open", "high", "low", "close", "volume"))

    bounds_ok = (
        (df["low"] <= df["open"]) & (df["open"] <= df["high"]) &
        (df["low"] <= df["close"]) & (df["close"] <= df["high"])
    )
    vol_ok = df["volume"] >= 0
    df = df[bounds_ok & vol_ok]

    df = df.sort_values("timestamp", ascending=True)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return df

def _validate_monotonic(df: pd.DataFrame, where: str) -> None:
    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError(f"{where} timestamps are not strictly ascending.")
    if (df["timestamp"].diff().dt.total_seconds().fillna(0) < 0).any():
        raise ValueError(f"{where} contains backward time jumps.")

def _read_excel_strict(
    xlsx_path: str,
    symbol: str,
    tf: str,
    engine: str = "openpyxl",
) -> pd.DataFrame:
    if not xlsx_path or not os.path.exists(xlsx_path):
        raise FileNotFoundError(f"Excel file not found: {xlsx_path}")

    sheet = _resolve_sheet_name(xlsx_path, symbol, tf, engine)
    raw = pd.read_excel(xlsx_path, sheet_name=sheet, engine=engine)

    # map/validate
    df = _ensure_required_columns(raw, f"Sheet '{sheet}' in {xlsx_path}")
    df = _parse_and_clean_strict(df)
    _validate_monotonic(df, f"Sheet '{sheet}'")
    df = df.astype({
        "open": "float64", "high": "float64",
        "low": "float64", "close": "float64", "volume": "float64",
    })
    return df.loc[:, list(REQUIRED_COLUMNS)]


# ---- CSV helpers ----
def _csv_path(symbol: str, tf: str) -> str:
    # ใช้ absolute path อ้างอิงโฟลเดอร์ของโมดูลนี้ (กัน CWD เพี้ยนตอนรัน cron)
    base = pathlib.Path(__file__).resolve().parent  # app/analysis
    data_dir = (base.parent / "data").resolve()    # app/data
    fname = f"{symbol.upper().replace(':','').replace('/','')}_{tf.upper()}.csv"
    return str((data_dir / fname))

def _read_csv_strict(symbol: str, tf: str) -> pd.DataFrame:
    path = _csv_path(symbol, tf)
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV not found: {path}")

    raw = pd.read_csv(path)
    raw.columns = [str(c).lower() for c in raw.columns]
    if "timestamp" not in raw.columns and "date" in raw.columns:
        raw = raw.rename(columns={"date": "timestamp"})

    df = _ensure_required_columns(raw, f"CSV '{path}'")
    df = _parse_and_clean_strict(df)
    _validate_monotonic(df, f"CSV '{path}'")
    return df.loc[:, list(REQUIRED_COLUMNS)]


# ✅ Resample 1D -> 1W
def _resample_to_1w(df_1d: pd.DataFrame) -> pd.DataFrame:
    if df_1d is None or df_1d.empty:
        raise ValueError("cannot resample 1W: 1D dataframe is empty")
    df = (
        df_1d.set_index("timestamp")
        .resample("1W")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("open", "high", "low", "close", "volume")).reset_index(drop=True)
    return df.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]]


# ========= Real-time provider chain (Binance first, pluggable) =========
def _tf_to_exchange_interval(tf: str) -> str:
    """Map '1H','4H','1D','1W' -> exchange interval string (Binance-compatible)."""
    t = (tf or "").strip().upper()
    return {
        "1H": "1h",
        "4H": "4h",
        "1D": "1d",
        "1W": "1w",
    }.get(t, "1d")

def _fetch_ohlcv_binance(symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV from Binance public endpoint (api/v3/klines).
    Returns DataFrame or None on failure.
    """
    import requests  # local import เพื่อลด dependency ตอนใช้โหมดไฟล์
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": min(int(limit), 1000)}
    try:
        r = requests.get(url, params=params, timeout=REALTIME_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        rows = []
        for k in data:
            # kline spec: [openTime, open, high, low, close, volume, closeTime, ...]
            rows.append({
                "timestamp": pd.to_datetime(k[0], unit="ms", utc=True),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        return df
    except Exception:
        return None

def _postprocess_realtime_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Make sure columns/types/order match REQUIRED_COLUMNS and clean like strict readers."""
    if df is None or df.empty:
        return None
    try:
        df = df.loc[:, list(REQUIRED_COLUMNS)]
        df = _parse_and_clean_strict(df)
        _validate_monotonic(df, "realtime")
        df = df.astype({
            "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64",
        })
        return df
    except Exception:
        return None

def _fetch_from_providers(symbol: str, tf: str, limit: int) -> Optional[pd.DataFrame]:
    """
    Try providers in order from REALTIME_PROVIDERS.
    Currently implemented: 'binance'
    Others will be skipped (placeholder for future).
    """
    interval = _tf_to_exchange_interval(tf)
    for p in REALTIME_PROVIDERS:
        if p == "binance":
            df = _fetch_ohlcv_binance(symbol, interval, limit)
        else:
            # Placeholder for future providers: okx/bybit/etc.
            df = None

        df = _postprocess_realtime_df(df) if df is not None else None
        if df is not None and not df.empty:
            return df
    return None


# ---- Main (on-demand loader; ไม่พึ่ง background) ----
def get_data(
    symbol: str,
    tf: Literal["1H", "4H", "1D", "1W"],
    *,
    xlsx_path: Optional[str] = None,
    engine: str = "openpyxl",
) -> pd.DataFrame:
    """
    Load OHLCV data.

    Modes:
      - Default (REALTIME != '1'): Excel → CSV → (for 1W) resample from 1D
      - Real-time (REALTIME == '1'): Provider chain (e.g., Binance). If all providers fail → fallback to files.

    Returns DataFrame with columns: timestamp(UTC), open, high, low, close, volume
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

    # ========= Real-time first if enabled =========
    if REALTIME_ON:
        df_rt = _fetch_from_providers(symbol, tf_u, REALTIME_LIMIT)
        if df_rt is not None and not df_rt.empty:
            return df_rt
        # ถ้า API ล้มเหลว → ตกกลับไปใช้ไฟล์ต่อด้านล่าง

    # ========= File-based flow =========
    # 1) ลอง Excel ก่อน
    path = xlsx_path or DATA_PATH_DEFAULT

    def _try_excel(sym: str, tf_: str) -> pd.DataFrame | None:
        try:
            return _read_excel_strict(path, sym, tf_, engine=engine)
        except Exception:
            return None

    def _try_csv(sym: str, tf_: str) -> pd.DataFrame | None:
        try:
            return _read_csv_strict(sym, tf_)
        except Exception:
            return None

    # ----- 1H / 4H / 1D -----
    if tf_u in ("1H", "4H", "1D"):
        df = _try_excel(symbol, tf_u)
        if df is None or df.empty:
            df = _try_csv(symbol, tf_u)
        if df is None:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
        return df

    # ----- 1W -----
    # ลองอ่านชีท 1W โดยตรง
    df_1w = _try_excel(symbol, "1W")
    if df_1w is not None and not df_1w.empty:
        return df_1w

    # ถ้าไม่มี ให้ resample จาก 1D (Excel หรือ CSV)
    df_1d = _try_excel(symbol, "1D")
    if df_1d is None or df_1d.empty:
        df_1d = _try_csv(symbol, "1D")
    if df_1d is None or df_1d.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    return _resample_to_1w(df_1d)


# ====================== OPTIONAL: Background updater/caching ======================
# ใช้สำหรับ worker.py เท่านั้น; ถ้าไม่เรียก start_* ก็ไม่กระทบของเดิม
_CACHE: Dict[Tuple[str, str], pd.DataFrame] = {}
_LAST_UPDATED: Dict[Tuple[str, str], float] = {}
_TASKS: List[asyncio.Task] = []

def _cache_set(symbol: str, tf: str, df: pd.DataFrame) -> None:
    key = (symbol.upper(), tf.upper())
    _CACHE[key] = df
    _LAST_UPDATED[key] = time.time()

def get_last_updated(symbol: str, tf: str) -> Optional[float]:
    """คืนค่า epoch seconds ของเวลาที่ cache ถูกอัปเดตล่าสุด (ถ้าไม่มีคืน None)"""
    return _LAST_UPDATED.get((symbol.upper(), tf.upper()))

def _seconds_until_next_bar(tf: str) -> int:
    """
    รอให้ตรงขอบแท่ง: คำนวณเวลาถึงแท่งถัดไป (เผื่อ repaint)
    รองรับโหมด debug ผ่าน ENV: FORCE_NEXTBAR_SECONDS (>0 จะใช้ค่านี้แทน)
    """
    try:
        force = int(os.getenv("FORCE_NEXTBAR_SECONDS", "0") or "0")
    except ValueError:
        force = 0
    if force > 0:
        return max(1, force)

    now = int(time.time())
    step = _TIMEFRAME_SECONDS.get(tf.upper(), 3600)
    next_cut = math.ceil(now / step) * step
    wait = max(1, next_cut - now)
    return wait + 1  # เผื่อ latency provider เล็กน้อย

async def _update_once(symbol: str, tf: str, limit: int) -> None:
    """ดึงข้อมูลตามโหมด (realtime/file) แล้วเก็บลง cache"""
    df: Optional[pd.DataFrame] = None

    # โหมด realtime ก่อน (ถ้าเปิด)
    if REALTIME_ON:
        df = _fetch_from_providers(symbol, tf, limit)

    # ถ้าไม่ได้ ให้ fallback ไปอ่านไฟล์ (on-demand reader)
    if df is None or df.empty:
        try:
            df = get_data(symbol, tf)
        except Exception:
            df = None

    if df is not None and not df.empty:
        _cache_set(symbol, tf, df)

def _update_blocking_wrapper(symbol: str, tf: str, limit: int) -> None:
    """ตัวหุ้มสำหรับเรียกใน thread (เพราะ fetch บางส่วนเป็น sync)"""
    try:
        df: Optional[pd.DataFrame] = None
        if REALTIME_ON:
            df = _fetch_from_providers(symbol, tf, limit)
        if df is None or df.empty:
            df = get_data(symbol, tf)  # fallback file-based
        if df is not None and not df.empty:
            _cache_set(symbol, tf, df)
    except Exception:
        pass

async def _run_stream(symbol: str, tf: str) -> None:
    """ลูป background: อุ่นข้อมูล → รอถึงขอบแท่ง → อัปเดตรอบถัดไป"""
    # อุ่นรอบแรก
    await asyncio.to_thread(_update_blocking_wrapper, symbol, tf, _BACKGROUND_WARM_LIMIT)
    # วนลูปอัปเดตตามรอบแท่ง
    while True:
        try:
            await asyncio.sleep(_seconds_until_next_bar(tf))
            await asyncio.to_thread(_update_blocking_wrapper, symbol, tf, _BACKGROUND_CYCLE_LIMIT)
        except asyncio.CancelledError:
            break
        except Exception:
            # กลืน error ไว้ใน loop เพื่อให้ลูปรอด
            await asyncio.sleep(2)

async def start_timeframe_service(pairs: List[Tuple[str, str]]) -> None:
    """
    เริ่ม background updater สำหรับคู่เหรียญ/TF ที่กำหนด
    - ไม่จำเป็นต้องเปิด REALTIME ก็ได้ (จะอ่านไฟล์เป็นหลัก) แต่เปิดไว้จะสดกว่า
    - ถ้าเรียกซ้ำและมี tasks อยู่แล้ว จะไม่สร้างซ้ำ
    """
    global _TASKS
    if _TASKS:
        return
    for sym, tf in pairs:
        t = asyncio.create_task(_run_stream(sym, tf))
        _TASKS.append(t)

async def stop_timeframe_service() -> None:
    """ยกเลิก task ทั้งหมดอย่างปลอดภัย"""
    global _TASKS
    for t in _TASKS:
        t.cancel()
    await asyncio.gather(*_TASKS, return_exceptions=True)
    _TASKS.clear()
