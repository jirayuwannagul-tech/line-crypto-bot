# app/analysis/timeframes.py
from __future__ import annotations

import os
from typing import Literal, Optional, Sequence

import pandas as pd

try:
    import ccxt  # fallback ดึงสดจาก Binance
except Exception:  # pragma: no cover
    ccxt = None

# ---- Public API ----
__all__ = [
    "get_data",
    "SUPPORTED_TF",
    "RequiredColumnsMissing",
]

# ---- Config ----
DATA_PATH_DEFAULT = os.getenv("HISTORICAL_XLSX_PATH", "app/data/historical.xlsx")
SUPPORTED_TF: tuple[str, ...] = ("1H", "4H", "1D")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")

# ---- Errors ----
class RequiredColumnsMissing(ValueError):
    """Raised when required OHLCV columns are missing in Excel sheet."""
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
    return df.loc[:, list(REQUIRED_COLUMNS)]

def _parse_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.assign(timestamp=ts)

    # drop invalid
    df = df.dropna(subset=list(REQUIRED_COLUMNS))

    # cast numeric
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("open", "high", "low", "close", "volume"))

    # sanity checks
    mask_bounds = (
        (df["low"] <= df["open"]) & (df["low"] <= df["close"]) &
        (df["high"] >= df["open"]) & (df["high"] >= df["close"])
    )
    mask_vol = df["volume"] >= 0
    df = df[mask_bounds & mask_vol]

    # sort & dedup
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
    if "/" in symbol:
        return symbol.upper()
    s = symbol.upper()
    for quote in ("USDT", "BUSD", "USDC"):
        if s.endswith(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"
    return s

def _fetch_ccxt_binance(symbol: str, tf: str, limit: int = 1500) -> pd.DataFrame:
    if ccxt is None:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    try:
        sym = _norm_symbol_ccxt(symbol)
        ccxt_tf = _norm_tf_to_ccxt(tf)
        ex = ccxt.binance({"enableRateLimit": True})
        raw = ex.fetch_ohlcv(sym, timeframe=ccxt_tf, limit=limit)  # [[ts,o,h,l,c,v], ...]
    except Exception:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    if not raw:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop(columns=["ts"])
    df = df.loc[:, list(REQUIRED_COLUMNS)]
    return _parse_and_clean(df)

def _read_excel_if_available(
    xlsx_path: str,
    symbol: str,
    tf: str,
    engine: str = "openpyxl",
) -> Optional[pd.DataFrame]:
    if not xlsx_path or not os.path.exists(xlsx_path):
        return None

    sheet = _sheet_name(symbol, tf)
    try:
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, engine=engine)
    except (ValueError, FileNotFoundError):
        return None

    try:
        df = _ensure_required_columns(raw, sheet)
        df = _parse_and_clean(df)
        _validate_monotonic(df, sheet)
        df = df.astype({
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        })
        return df.loc[:, list(REQUIRED_COLUMNS)]
    except Exception:
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

    Priority:
      1) ถ้ามี Excel sheet → ใช้
      2) ถ้าไม่เจอ/ผิดพลาด → fallback ccxt (Binance)

    Returns DataFrame: timestamp(UTC), open, high, low, close, volume
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

    path = xlsx_path or DATA_PATH_DEFAULT
    df_excel = _read_excel_if_available(path, symbol, tf_u, engine=engine)
    if df_excel is not None and len(df_excel) > 0:
        return df_excel

    df_live = _fetch_ccxt_binance(symbol, tf_u, limit=limit)
    return df_live.sort_values("timestamp").reset_index(drop=True)
