# app/analysis/timeframes.py
from __future__ import annotations

import os
import re
from typing import Literal, Optional, Sequence

import pandas as pd

# ---- Public API ----
__all__ = [
    "get_data",
    "SUPPORTED_TF",
    "RequiredColumnsMissing",
]

# ---- Config ----
DATA_PATH_DEFAULT = os.getenv("HISTORICAL_XLSX_PATH", "app/data/historical.xlsx")
# ✅ รองรับ 1W
SUPPORTED_TF: tuple[str, ...] = ("1H", "4H", "1D", "1W")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")


# ---- Errors ----
class RequiredColumnsMissing(ValueError):
    """Raised when required OHLCV columns are missing in Excel sheet."""
    pass


# ---- Helpers (Excel only, rules-only) ----
def _sheet_name(symbol: str, tf: str) -> str:
    sym = symbol.upper().replace(":", "").replace("/", "")
    tf_norm = tf.upper()
    return f"{sym}_{tf_norm}"


def _normalize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


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


def _ensure_required_columns(df: pd.DataFrame, sheet: str) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise RequiredColumnsMissing(
            f"Sheet '{sheet}' missing columns: {missing}. Expected: {list(REQUIRED_COLUMNS)}"
        )
    return df.loc[:, list(REQUIRED_COLUMNS)]


def _parse_and_clean_strict(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.assign(timestamp=ts).dropna(subset=["timestamp"])

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


def _validate_monotonic(df: pd.DataFrame, sheet: str) -> None:
    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError(f"Sheet '{sheet}' timestamps are not strictly ascending.")
    if (df["timestamp"].diff().dt.total_seconds().fillna(0) < 0).any():
        raise ValueError(f"Sheet '{sheet}' contains backward time jumps.")


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

    df = _ensure_required_columns(raw, sheet)
    df = _parse_and_clean_strict(df)
    _validate_monotonic(df, sheet)

    df = df.astype({
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "float64",
    })
    return df.loc[:, list(REQUIRED_COLUMNS)]


# ✅ NEW: resample 1D -> 1W (ถ้าไม่มีชีท 1W)
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


# ---- Main (Rules-Only) ----
def get_data(
    symbol: str,
    tf: Literal["1H", "4H", "1D", "1W"],
    *,
    xlsx_path: Optional[str] = None,
    engine: str = "openpyxl",
) -> pd.DataFrame:
    """
    Load OHLCV data from Excel ONLY (rules-only).
    - ถ้า 1W ไม่มีใน Excel → จะ resample จาก 1D ให้อัตโนมัติ
    - ไม่ fallback ไปที่แหล่งอื่น
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

    path = xlsx_path or DATA_PATH_DEFAULT

    # อ่านตรง ๆ สำหรับ 1H/4H/1D
    if tf_u in ("1H", "4H", "1D"):
        return _read_excel_strict(path, symbol, tf_u, engine=engine)

    # 1W: ลองอ่านชีท 1W → ถ้าไม่เจอให้ resample จาก 1D
    try:
        return _read_excel_strict(path, symbol, "1W", engine=engine)
    except Exception:
        df_1d = _read_excel_strict(path, symbol, "1D", engine=engine)
        return _resample_to_1w(df_1d)
