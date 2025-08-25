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
SUPPORTED_TF: tuple[str, ...] = ("1H", "4H", "1D")
REQUIRED_COLUMNS: Sequence[str] = ("timestamp", "open", "high", "low", "close", "volume")


# ---- Errors ----
class RequiredColumnsMissing(ValueError):
    """Raised when required OHLCV columns are missing in Excel sheet."""
    pass


# ---- Helpers (Excel only, rules-only) ----
def _sheet_name(symbol: str, tf: str) -> str:
    """ชื่อชีทเป้าหมายแบบเข้มงวด (มาตรฐาน: BTCUSDT_1D)"""
    sym = symbol.upper().replace(":", "").replace("/", "")
    tf_norm = tf.upper()
    return f"{sym}_{tf_norm}"


def _normalize(name: str) -> str:
    """แปลงชื่อชีทให้เทียบกันได้ง่าย: ตัดอักขระที่ไม่ใช่ a-z0-9 และทำเป็นตัวพิมพ์เล็ก"""
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


def _resolve_sheet_name(
    xlsx_path: str,
    symbol: str,
    tf: str,
    engine: Optional[str],
) -> str:
    """
    พยายามหา sheet ที่ตรง/ใกล้เคียง f'{symbol}_{tf}' (รองรับ -, ช่องว่าง, สลับตำแหน่ง ฯลฯ)
    ลำดับการหา:
      1) แมตช์ normalize ตรงกับชุด target variants
      2) ถ้าไม่เจอ หา sheet ที่มีทั้ง 'symbol' และ 'tf' (แบบ normalize) อยู่ในชื่อ
      3) ถ้าไม่เจอจริง ๆ → แจ้งรายการชีททั้งหมดเพื่อ debug
    """
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
    # map normalize -> real sheet name
    by_norm = {_normalize(s): s for s in xls.sheet_names}

    # 1) ตรงตัวแบบ normalize
    for t in target_norms:
        if t in by_norm:
            return by_norm[t]

    # 2) มีทั้ง symbol และ tf อยู่ในชื่อ (แบบ normalize)
    sym_n = _normalize(symbol_u)
    tf_n = _normalize(tf_u)
    for nrm, real in by_norm.items():
        if sym_n in nrm and tf_n in nrm:
            return real

    # 3) ไม่พบ → โยน error พร้อมช่วย debug
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
    # 1) parse timestamp (UTC) — แปลงไม่ได้ให้ทิ้ง
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.assign(timestamp=ts).dropna(subset=["timestamp"])

    # 2) cast numeric — แปลงไม่ได้ให้เป็น NaN แล้วทิ้ง
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=("open", "high", "low", "close", "volume"))

    # 3) กฎขอบเขต OHLC (เคร่งครัด ไม่มี heuristic)
    #    low <= {open,close} <= high  และ volume >= 0
    bounds_ok = (
        (df["low"] <= df["open"]) & (df["open"] <= df["high"]) &
        (df["low"] <= df["close"]) & (df["close"] <= df["high"])
    )
    vol_ok = df["volume"] >= 0
    df = df[bounds_ok & vol_ok]

    # 4) sort & dedup (ตาม timestamp)
    df = df.sort_values("timestamp", ascending=True)
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return df


def _validate_monotonic(df: pd.DataFrame, sheet: str) -> None:
    # เวลาต้องเพิ่มขึ้นตลอด (ไม่ถอยหลัง)
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

    # ยืดหยุ่นชื่อชีท แต่ยัง “rules-only”
    sheet = _resolve_sheet_name(xlsx_path, symbol, tf, engine)

    raw = pd.read_excel(xlsx_path, sheet_name=sheet, engine=engine)

    df = _ensure_required_columns(raw, sheet)
    df = _parse_and_clean_strict(df)
    _validate_monotonic(df, sheet)

    # enforce dtypes
    df = df.astype({
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "float64",
    })
    return df.loc[:, list(REQUIRED_COLUMNS)]


# ---- Main (Rules-Only) ----
def get_data(
    symbol: str,
    tf: Literal["1H", "4H", "1D"],
    *,
    xlsx_path: Optional[str] = None,
    engine: str = "openpyxl",
) -> pd.DataFrame:
    """
    Load OHLCV data from Excel ONLY (rules-only).
    - ไม่ fallback ไปที่แหล่งอื่น
    - ถ้าไม่มีไฟล์/ชีต/คอลัมน์/เวลาผิด → โยน error ทันที
    Returns: DataFrame['timestamp','open','high','low','close','volume'] (UTC, strict)
    """
    tf_u = tf.upper()
    if tf_u not in SUPPORTED_TF:
        raise ValueError(f"Unsupported timeframe '{tf}'. Supported: {SUPPORTED_TF}")

    path = xlsx_path or DATA_PATH_DEFAULT
    return _read_excel_strict(path, symbol, tf_u, engine=engine)
