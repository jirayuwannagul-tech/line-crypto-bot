from __future__ import annotations

from typing import Optional
import re
import pandas as pd

# ==============================
# Public API
# ==============================
__all__ = ["get_ohlcv_ccxt_safe"]


# ---------- Helpers ----------
_BINANCE_INTERVAL = {
    "1M": "1m",
    "5M": "5m",
    "15M": "15m",
    "30M": "30m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1w",
}

def _to_binance_symbol(symbol: str) -> str:
    """
    Normalizes pair to Binance format.
    - 'BTC/USDT' -> 'BTCUSDT'
    - 'BTCUSDT'  -> 'BTCUSDT'
    - 'BTC'      -> 'BTCUSDT' (default quote = USDT)
    """
    s = (symbol or "").strip().upper()
    if "/" in s or ":" in s or "-" in s:
        s = s.replace(":", "/").replace("-", "/")
        parts = [p for p in s.split("/") if p]
        if len(parts) == 2:
            return f"{parts[0]}{parts[1]}"
    # already like BTCUSDT?
    if re.fullmatch(r"[A-Z0-9]{5,}", s):
        return s
    return f"{s}USDT"


def _interval_to_binance(tf: str) -> str:
    return _BINANCE_INTERVAL.get((tf or "").upper(), "1d")


def _to_dataframe_ohlcv(rows) -> pd.DataFrame:
    """
    rows: list of klines from Binance or ccxt:
      [openTime, open, high, low, close, volume, closeTime, ...]
    """
    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    data = []
    for k in rows:
        data.append({
            "timestamp": pd.to_datetime(k[0], unit="ms", utc=True),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    # basic cleaning / sort
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)
    return df


# ---------- Fallback: Binance REST ----------
def _fetch_via_binance_rest(symbol: str, tf: str, limit: int) -> Optional[pd.DataFrame]:
    import requests  # lazy import
    sym = _to_binance_symbol(symbol)
    interval = _interval_to_binance(tf)
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": interval, "limit": max(50, min(int(limit or 500), 1000))}
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        return _to_dataframe_ohlcv(r.json())
    except Exception:
        return None


# ---------- Try ccxt first, then fallback ----------
def get_ohlcv_ccxt_safe(symbol: str, tf: str, limit: int = 500) -> pd.DataFrame:
    """
    Returns pandas.DataFrame with columns:
      timestamp(UTC), open, high, low, close, volume

    Strategy:
      1) Try ccxt.binance().fetch_ohlcv() if ccxt is installed
      2) Fallback -> Binance REST /api/v3/klines
    """
    # 1) ccxt path (optional)
    try:
        import ccxt  # type: ignore
        binance = ccxt.binance({"options": {"defaultType": "spot"}})
        sym = (symbol or "").upper()
        if "/" not in sym:
            # make sure ccxt format is BASE/QUOTE (e.g., BTC/USDT)
            if sym.endswith("USDT") and len(sym) > 4:
                sym = f"{sym[:-4]}/USDT"
            else:
                sym = f"{sym}/USDT"
        timeframe = (tf or "1D").upper()
        # Map to ccxt timeframe
        ccxt_tf_map = {
            "1M": "1m",
            "5M": "5m",
            "15M": "15m",
            "30M": "30m",
            "1H": "1h",
            "4H": "4h",
            "1D": "1d",
            "1W": "1w",
        }
        ccxt_tf = ccxt_tf_map.get(timeframe, "1d")
        candles = binance.fetch_ohlcv(sym, timeframe=ccxt_tf, limit=max(50, min(int(limit or 500), 1000)))
        df = _to_dataframe_ohlcv(candles)
        if not df.empty:
            return df
    except Exception:
        # ignore and fallback to REST
        pass

    # 2) REST fallback
    df2 = _fetch_via_binance_rest(symbol, tf, limit)
    if df2 is not None and not df2.empty:
        return df2

    # empty frame on failure
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
