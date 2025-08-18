# app/utils/crypto_price.py
# ============================================
# LAYER: PRICE FETCHER / ADAPTER (Coingecko-ready)
# ============================================
from __future__ import annotations
from typing import Dict, Any, Optional, List
import httpx
import pandas as pd

from app.config.symbols import resolve_symbol, is_supported

# ===== CONFIG / ENDPOINTS =====
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEFAULT_VS = "usd"

__all__ = [
    "fetch_spot",
    "fetch_ohlcv",
    "fetch_close_series",
    "get_price_text",
    "COINGECKO_BASE",
    "DEFAULT_VS",
]

# ===== HTTP CLIENT =====
def _http_get(url: str, params: Dict[str, Any]) -> Any:
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code} GET {url} params={params}") from e
    except Exception as e:
        raise RuntimeError(f"Request failed GET {url} params={params}") from e

# ===== SPOT PRICE =====
def fetch_spot(symbol_id: str, vs: str = DEFAULT_VS) -> Optional[float]:
    """
    ดึงราคา spot ปัจจุบันจาก /simple/price
    รับ symbol_id รูปแบบ coingecko เช่น 'bitcoin'
    คืน float หรือ None
    """
    url = f"{COINGECKO_BASE}/simple/price"
    data = _http_get(url, {"ids": symbol_id, "vs_currencies": vs})
    val = data.get(symbol_id, {}).get(vs)
    return float(val) if val is not None else None

# ===== OHLC =====
def fetch_ohlcv(symbol_id: str, days: int = 1, vs: str = DEFAULT_VS) -> pd.DataFrame:
    """
    ดึงแท่งเทียนจาก /coins/{id}/ohlc
    days รองรับ {1, 7, 14, 30, 90, 180, 365}
    คืน DataFrame คอลัมน์: ['open','high','low','close','volume']
    """
    if days not in (1, 7, 14, 30, 90, 180, 365):
        days = 1
    url = f"{COINGECKO_BASE}/coins/{symbol_id}/ohlc"
    raw = _http_get(url, {"vs_currency": vs, "days": days})
    if not raw:
        raise RuntimeError("Empty OHLC response")

    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    df["volume"] = pd.NA  # Coingecko endpoint นี้ไม่ให้ volume
    return df

# ===== CLOSE SERIES (FALLBACK) =====
def fetch_close_series(symbol_id: str, days: int = 1, vs: str = DEFAULT_VS) -> pd.DataFrame:
    """
    ดึงเส้นราคาปิดจาก /coins/{id}/market_chart → columns: ['close']
    """
    url = f"{COINGECKO_BASE}/coins/{symbol_id}/market_chart"
    raw = _http_get(url, {"vs_currency": vs, "days": days})
    prices: List[List[float]] = raw.get("prices", [])
    if not prices:
        raise RuntimeError("Empty market_chart.prices")

    df = pd.DataFrame(prices, columns=["ts", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df

# ===== HELPER FOR LINE WEBHOOK =====
def get_price_text(symbol: str, vs: str = DEFAULT_VS) -> str:
    """
    รับ 'BTC' หรือ id โดยตรง → คืนสตริงสั้น ๆ พร้อมราคาเช่น 'BTC ~ 115,118.00 USD'
    ใช้ resolve_symbol ถ้าเป็นตัวย่อ (BTC/ETH/…)
    """
    sym = symbol.upper().strip()
    try:
        symbol_id = resolve_symbol(sym) if is_supported(sym) else sym
        price = fetch_spot(symbol_id, vs=vs)
        if price is None:
            return f"{sym} ~ N/A"
        # แสดงทศนิยม 2 ตำแหน่ง (พอสำหรับข้อความสั้น ๆ)
        return f"{sym} ~ {price:,.2f} {vs.upper()}"
    except Exception:
        return f"{sym} ~ N/A"
