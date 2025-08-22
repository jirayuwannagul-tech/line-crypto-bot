# app/analysis/timeframes.py
from __future__ import annotations

import os
from typing import Literal, Optional, Sequence

import pandas as pd

try:
    import ccxt  # ใช้ fallback ดึงสดจาก Binance
except Exception:  # pragma: no cover
    ccxt = None

# ---- Public API ----
__all__ = ["get_data", "SUPPORTED_TF", "RequiredColumnsMissing"]

# ---- Config ----
DATA_PATH_DEFAULT = os.getenv("HISTORICAL_XLSX_PATH", "app/data/historical.xlsx")
SUPPORTED_TF = ("1H", "4H", "1D")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")

# ---- Errors ----
class RequiredColumnsMissing(ValueError):
    pass

# ---- Internal helpers (Excel) ----
def _sheet_name(symbol: str, tf: str) -> str:
    sym = symbol.upper().replace(":", "").replace("/", "")
    tf_norm = tf.upper()
    return f"{sym}_{tf_norm}"

def _ensure_required_columns(df: pd.DataFrame, sheet: str) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RequiredColumnsMissing(
            f"Sheet '{sheet}' missing columns: {missing}. Expected: {list(REQUIRED_COLUMNS)}"
        )
    # Reorder columns
    return df.loc[:, list(REQUIRED_COLUMNS)]

def _parse_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    # timestamp -> datetime (UTC tz-aware); ถ้า naive จะสมมติเป็น UTC
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.assign(timestamp=ts)

    # drop rows with bad timestamp or any NaN in required fields
    df = df.dropna(subset=list(REQUIRED_COLUMNS))

    # cast numeric columns
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("open", "high", "low", "close", "volume"))

    # basic sanity: low <= open/close <= high ; volume >= 0
    mask_bounds = (
        (df["low"] <= df["open"]) & (df["low"] <= df["close"]) &
        (df["high"] >= df["open"]) & (df["high"] >= df["close"])
    )
    mask_vol = df["volume"] >= 0
    df = df[mask_bounds & mask_vol]

    # sort & deduplicate
    df = df.sort_values("timestamp", ascending=True)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return df

def _validate_monotonic(df: pd.DataFrame, sheet: str) -> None:
    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError(f"Sheet '{sheet}' timestamps are not strictly ascending.")
    if (df["timestamp"].diff().dt.total_seconds().fillna(0) < 0).any():
        raise ValueError(f"Sheet '{sheet}' contains backward time jumps.")

# ---- Internal helpers (ccxt fallback) ----
_TF_MAP = {"1H": "1h", "4H": "4h", "1D": "1d"}

def _norm_tf_to_ccxt(tf: str) -> str:
    return _TF_MAP.get(tf.upper(), tf.lower())

def _norm_symbol_ccxt(symbol: str) -> str:
    """แปลง 'BTCUSDT' -> 'BTC/USDT' ให้เข้ากับ ccxt"""
    if "/" in symbol:
        return symbol.upper()
    s = symbol.upper()
    for quote in ("USDT", "BUSD", "USDC"):
        if s.endswith(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"
    return s

def _fetch_ccxt_binance(symbol: str, tf: str, limit: int = 1500) -> pd.DataFrame:
    """
    ดึง OHLCV สดจาก Binance ผ่าน ccxt → คืน DataFrame ตาม schema REQUIRED_COLUMNS
    timestamp เป็น UTC tz-aware (datetime64[ns, UTC])
    """
    if ccxt is None:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    sym = _norm_symbol_ccxt(symbol)
    ccxt_tf = _norm_tf_to_ccxt(tf)

    ex = ccxt.binance({"enableRateLimit": True})
    raw = ex.fetch_ohlcv(sym, timeframe=ccxt_tf, limit=limit)  # [[ts,o,h,l,c,v], ...]
    if not raw:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)  # tz-aware
    df = df.drop(columns=["ts"])
    df = df.loc[:, list(REQUIRED_COLUMNS)]
    df = _parse_and_clean(df)
    return df

def _read_excel_if_available(xlsx_path: str, symbol: str, tf: str, engine: str) -> Optional[pd.DataFrame]:
    """พยายามอ่านจาก Excel ถ้ามีชีทอยู่ คืน DataFrame หลัง clean/validate; ถ้าไม่มีคืน None."""
    if not xlsx_path or not os.path.exists(xlsx_path):
        return None

    sheet = _sheet_name(symbol, tf)
    try:
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, engine=engine)
    except ValueError:
        # sheet ไม่เจอ
        return None
    except FileNotFoundError:
        return None

    try:
        df = _ensure_required_columns(raw, sheet)
        df = _parse_and_clean(df)
        _validate_monotonic(df, sheet)
        # Ensure dtypes & column order
        df = df.loc[:, list(REQUIRED_COLUMNS)]
        df = df.astype({
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        })
        return df
    except Exception:
        # ถ้าไฟล์เพี้ยน ให้ fallback ไป ccxt
        return None

# ---- Main function ----
def get_data(
    symbol: str,
    tf: Literal["1H", "4H", "1D"],
    *,
    xlsx_path: Optional[str] = None,
    engine: str = "openpyxl",
    limit: int = 1500,
) -> pd.DataFrame:
    """
    Load OHLCV data for a symbol & timeframe.

    ลำดับความพยายาม:
      1) ถ้ามี xlsx_path และมีชีทที่ตรง → อ่านจาก Excel แล้ว clean/validate
      2) ถ้าไม่มี/อ่านไม่ได้/ข้อมูลว่าง → ดึงสดจาก Binance ผ่าน ccxt

    Returns
    -------
    pandas.DataFrame
        Columns: timestamp (UTC, datetime64[ns, UTC]), open, high, low, close, volume
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

    # 1) Excel ก่อน (ถ้ามี)
    path = xlsx_path or DATA_PATH_DEFAULT
    df_excel = _read_excel_if_available(path, symbol, tf_u, engine=engine)
    if df_excel is not None and len(df_excel) > 0:
        return df_excel

    # 2) สดจาก ccxt/binance
    df_live = _fetch_ccxt_binance(symbol, tf_u, limit=limit)
    # ให้ผลลัพธ์เรียงตามเวลา
    return df_live.sort_values("timestamp").reset_index(drop=True)
