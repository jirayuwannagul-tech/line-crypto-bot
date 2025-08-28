from __future__ import annotations

from typing import Optional
import re
import pandas as pd

__all__ = [
    "get_ohlcv_ccxt_safe",
    "fetch_spot_text",
    "get_spot_ccxt",
    "get_spot_text_ccxt",
    "get_price",
]

# ---- Map TF ----
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
    ส่งกลับสัญลักษณ์สำหรับ REST ของ Binance (เช่น BTCUSDT) จากอินพุตที่รับได้หลายรูปแบบ
    รองรับ 'BTCUSDT', 'BTC/USDT', 'BTC-USDT', 'BTC:USDT'
    """
    s = (symbol or "").strip().upper()
    if "/" in s or ":" in s or "-" in s:
        s = s.replace(":", "/").replace("-", "/")
        parts = [p for p in s.split("/") if p]
        if len(parts) == 2:
            return f"{parts[0]}{parts[1]}"
    if re.fullmatch(r"[A-Z0-9]{5,}", s):
        return s
    return f"{s}USDT"

def _to_display_pair(symbol: str) -> str:
    """สำหรับข้อความแสดงผล: คืนเป็นรูปแบบ BASE/QUOTE เสมอ"""
    s = (symbol or "").strip().upper()
    s = s.replace(":", "/").replace("-", "/")
    if "/" in s:
        base, quote = [p for p in s.split("/") if p][:2]
        return f"{base}/{quote}"
    # ไม่มี '/', เติม /USDT ให้ดูสวยงาม
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}/USDT"
    return f"{s}/USDT"

def _interval_to_binance(tf: str) -> str:
    return _BINANCE_INTERVAL.get((tf or "").upper(), "1d")

def _to_dataframe_ohlcv(rows) -> pd.DataFrame:
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
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)
    return df

# ---- REST fallback ----
def _fetch_via_binance_rest(symbol: str, tf: str, limit: int) -> Optional[pd.DataFrame]:
    import requests
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

# ---- Public: get_ohlcv_ccxt_safe ----
def get_ohlcv_ccxt_safe(symbol: str, tf: str, limit: int = 500) -> pd.DataFrame:
    """
    Returns DataFrame[timestamp, open, high, low, close, volume]
    Strategy:
      1) ccxt.binance().fetch_ohlcv() if available
      2) fallback -> Binance REST /api/v3/klines
    """
    try:
        import ccxt  # type: ignore
        binance = ccxt.binance({"options": {"defaultType": "spot"}})
        sym = (symbol or "").upper()
        if "/" not in sym:
            if sym.endswith("USDT") and len(sym) > 4:
                sym = f"{sym[:-4]}/USDT"
            else:
                sym = f"{sym}/USDT"
        ccxt_tf = _interval_to_binance(tf)
        candles = binance.fetch_ohlcv(sym, timeframe=ccxt_tf, limit=max(50, min(int(limit or 500), 1000)))
        df = _to_dataframe_ohlcv(candles)
        if not df.empty:
            return df
    except Exception:
        pass

    df2 = _fetch_via_binance_rest(symbol, tf, limit)
    if df2 is not None and not df2.empty:
        return df2
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

# ---- Public: spot price via ccxt (with REST fallback) ----
def get_spot_ccxt(symbol: str = "BTC/USDT") -> Optional[float]:
    """
    คืนราคาล่าสุด (float) จาก Binance ผ่าน ccxt; หาก ccxt ใช้ไม่ได้ ตกลง REST
    รองรับ 'BTCUSDT' และ 'BTC/USDT'
    """
    # 1) ccxt first
    try:
        import ccxt  # type: ignore
        binance = ccxt.binance({"options": {"defaultType": "spot"}})
        sym = (symbol or "").upper()
        if "/" not in sym:
            if sym.endswith("USDT") and len(sym) > 4:
                sym = f"{sym[:-4]}/USDT"
            else:
                sym = f"{sym}/USDT"
        ticker = binance.fetch_ticker(sym)
        px = float(ticker.get("last") or ticker.get("close") or ticker.get("info", {}).get("lastPrice"))
        if px > 0:
            return px
    except Exception:
        pass

    # 2) REST fallback
    try:
        import requests
        sym_rest = _to_binance_symbol(symbol)
        r = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": sym_rest}, timeout=8)
        r.raise_for_status()
        data = r.json()
        return float(data["price"])
    except Exception:
        return None

def get_spot_text_ccxt(symbol: str = "BTC/USDT") -> str:
    """
    คืนราคาล่าสุดแบบ string พร้อมหน่วย USDT และคงรูปแบบคู่เป็น BASE/QUOTE
    """
    px = get_spot_ccxt(symbol)
    display = _to_display_pair(symbol)
    if px is None:
        return f"{display} price unavailable"
    return f"{display} last price: {px:,.2f} USDT"

# ---- Public: fetch_spot_text (ใช้โดย chat router เดิม) ----
def fetch_spot_text(symbol: str) -> str:
    """
    คืนข้อความราคาล่าสุดแบบสั้นสำหรับห้องแชท เช่น:
    'BTC/USDT last price: 111,234.56 USDT'
    """
    import requests
    sym_rest = _to_binance_symbol(symbol)
    display = _to_display_pair(symbol)
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": sym_rest}, timeout=8)
        r.raise_for_status()
        data = r.json()
        px = float(data["price"])
        return f"{display} last price: {px:,.2f} USDT"
    except Exception as e:
        return f"{display} price unavailable: {e}"

# ---- Public: get_price (ใช้โดย jobs/watch_targets) ----
def get_price(symbol: str = "BTCUSDT", *, timeout_sec: Optional[float] = 10.0) -> float:
    """
    คืนราคาล่าสุดแบบ float
    - รองรับสัญลักษณ์ 'BTCUSDT' และ 'BTC/USDT'
    - ใช้ ccxt ก่อน ถ้าไม่ได้จะ fallback REST
    """
    px = get_spot_ccxt(symbol)
    if px is None:
        # ลอง REST ตรง ๆ อีกรอบตาม timeout ที่รับเข้ามา
        try:
            import requests
            sym_rest = _to_binance_symbol(symbol)
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": sym_rest},
                timeout=max(3, int(timeout_sec or 10)),
            )
            r.raise_for_status()
            data = r.json()
            px = float(data["price"])
        except Exception as e:
            raise RuntimeError(f"fetch price failed for {symbol}: {e}")
    return float(px)
