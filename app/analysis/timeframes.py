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
SUPPORTED_TF: tuple[str, ...] = ("1H", "4H", "1D", "1W")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")


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
    return os.path.join("app", "data", f"{symbol.upper().replace(':','').replace('/','')}_{tf.upper()}.csv")

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


# ---- Main ----
def get_data(
    symbol: str,
    tf: Literal["1H", "4H", "1D", "1W"],
    *,
    xlsx_path: Optional[str] = None,
    engine: str = "openpyxl",
) -> pd.DataFrame:
    """
    Load OHLCV data from Excel; fallback to CSV in app/data when Excel sheet missing.
    - ถ้า 1W ไม่มี → resample จาก 1D (Excel หรือ CSV)
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

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
