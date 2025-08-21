# app/analysis/timeframes.py
from __future__ import annotations

import os
from typing import Literal, Optional, Sequence, Dict

import pandas as pd

# ---- Public API ----
__all__ = ["get_data", "SUPPORTED_TF", "RequiredColumnsMissing"]

# ---- Config ----
DATA_PATH_DEFAULT = os.getenv("HISTORICAL_XLSX_PATH", "app/data/historical.xlsx")
SUPPORTED_TF = ("1H", "4H", "1D")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")


# ---- Errors ----
class RequiredColumnsMissing(ValueError):
    pass


# ---- Internal helpers ----
def _sheet_name(symbol: str, tf: str) -> str:
    sym = symbol.upper().replace(":", "").replace("/", "")
    tf_norm = tf.upper()
    return f"{sym}_{tf_norm}"


def _ensure_required_columns(df: pd.DataFrame, sheet: str) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RequiredColumnsMissing(
            f"Sheet '{sheet}' missing columns: {missing}. "
            f"Expected: {list(REQUIRED_COLUMNS)}"
        )
    # Reorder columns
    return df.loc[:, list(REQUIRED_COLUMNS)]


def _parse_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    # timestamp -> datetime (assume UTC if naive)
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.assign(timestamp=ts)

    # drop rows with bad timestamp or any NaN in required fields
    df = df.dropna(subset=list(REQUIRED_COLUMNS))

    # cast numeric columns
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("open", "high", "low", "close", "volume"))

    # basic sanity: low <= open/close <= high ; volume >= 0
    mask_bounds = (df["low"] <= df["open"]) & (df["low"] <= df["close"]) & \
                  (df["high"] >= df["open"]) & (df["high"] >= df["close"])
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


# ---- Main function ----
def get_data(
    symbol: str,
    tf: Literal["1H", "4H", "1D"],
    *,
    xlsx_path: Optional[str] = None,
    engine: str = "openpyxl",
) -> pd.DataFrame:
    """
    Load OHLCV data for a symbol & timeframe from app/data/historical.xlsx.

    Parameters
    ----------
    symbol : str
        e.g., "BTCUSDT"
    tf : {"1H","4H","1D"}
    xlsx_path : str, optional
        Override path to the Excel file. Defaults to DATA_PATH_DEFAULT.
    engine : str
        pandas Excel engine (default: openpyxl)

    Returns
    -------
    pandas.DataFrame
        Columns: timestamp (UTC, datetime64[ns, UTC]), open, high, low, close, volume

    Raises
    ------
    FileNotFoundError, RequiredColumnsMissing, ValueError
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

    path = xlsx_path or DATA_PATH_DEFAULT
    if not os.path.exists(path):
        raise FileNotFoundError(f"Excel file not found: {path}")

    sheet = _sheet_name(symbol, tf_u)
    try:
        raw = pd.read_excel(path, sheet_name=sheet, engine=engine)
    except ValueError as e:
        # pandas raises ValueError if sheet not found
        raise ValueError(f"Sheet '{sheet}' not found in {path}") from e

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
