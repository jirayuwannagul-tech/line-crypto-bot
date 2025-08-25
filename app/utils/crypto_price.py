# app/utils/crypto_price.py
import os
import time
import asyncio
import httpx
from typing import Optional, Dict, Tuple

_DEFAULT_VS = os.getenv("QUOTE_ASSET", "USDT").upper()
_PROVIDER   = os.getenv("PRICE_PROVIDER", "binance").lower()  # binance|coingecko
_PRICE_TTL  = int(os.getenv("PRICE_TTL_SECONDS", "15"))
_BINANCE_HOSTS = [
    os.getenv("BINANCE_HOST", "https://api.binance.com"),
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision",
]

_price_cache: Dict[str, Tuple[float, float]] = {}

def _cache_key(symbol: str, vs: str) -> str:
    return f"{symbol.upper()}-{vs.upper()}"

def _get_cached(symbol: str, vs: str) -> Optional[float]:
    row = _price_cache.get(_cache_key(symbol, vs))
    if not row:
        return None
    price, ts = row
    return price if (time.time() - ts) <= _PRICE_TTL else None

def _set_cache(symbol: str, vs: str, price: float) -> None:
    _price_cache[_cache_key(symbol, vs)] = (price, time.time())

async def _get_price_binance(symbol: str, vs: str) -> Optional[float]:
    pair = f"{symbol.upper()}{vs.upper()}"
    params = {"symbol": pair}
    headers = {"User-Agent": "line-crypto-bot/1.0"}
    backoffs = [0.5, 1.0]

    for base in _BINANCE_HOSTS:
        url = f"{base.rstrip('/')}/api/v3/ticker/price"
        for wait in [0.0] + backoffs:
            if wait:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(url, params=params, headers=headers)
            except httpx.RequestError:
                continue
            if r.status_code == 200:
                try:
                    j = r.json()
                    return float(j["price"])
                except Exception:
                    break
            if r.status_code in (400, 403, 404, 451):
                break
            if r.status_code == 429:
                continue
            break
    return None

async def _get_price_coingecko(symbol: str, vs: str) -> Optional[float]:
    vs_currency = "usd" if vs.upper() in ("USD", "USDT") else vs.lower()
    SYMBOL_MAP = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
        "ADA": "cardano", "XRP": "ripple", "SOL": "solana",
        "DOGE": "dogecoin", "SAND": "the-sandbox",
    }
    coin_id = SYMBOL_MAP.get(symbol.upper())
    if not coin_id:
        return None
    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"ids": coin_id, "vs_currencies": vs_currency})
        if r.status_code != 200:
            return None
        data = r.json()
        val = data.get(coin_id, {}).get(vs_currency)
        return float(val) if val is not None else None
    except Exception:
        return None

async def get_price(symbol: str, vs: str | None = None) -> Optional[float]:
    vs = (vs or _DEFAULT_VS).upper()
    cached = _get_cached(symbol, vs)
    if cached is not None:
        return cached

    order = [_PROVIDER, "coingecko" if _PROVIDER == "binance" else "binance"]
    price: Optional[float] = None
    for prov in order:
        if prov == "binance":
            price = await _get_price_binance(symbol, vs)
        elif prov == "coingecko":
            price = await _get_price_coingecko(symbol, vs)
        if price is not None:
            break
    if price is not None:
        _set_cache(symbol, vs, price)
    return price

async def get_price_text(symbol: str, vs: str | None = None) -> str:
    vs = (vs or _DEFAULT_VS).upper()
    price = await get_price(symbol, vs)
    if price is None:
        return f"❌ ไม่พบราคา {symbol.upper()}/{vs}"
    unit = "USD" if vs in ("USD", "USDT") else vs
    return f"💰 ราคา {symbol.upper()} ล่าสุด: {price:,.2f} {unit}"

# --- compat (async) ---
async def get_price_usd(symbol: str) -> Optional[float]:
    return await get_price(symbol, "USDT")

# --- compat (sync wrapper สำหรับ LINE webhook) ---
def fetch_price_text(symbol: str, vs: str | None = None) -> str:
    """เรียกใช้งาน get_price_text ในรูปแบบ synchronous"""
    try:
        return asyncio.run(get_price_text(symbol, vs))
    except RuntimeError:
        # ถ้า event loop เปิดอยู่ (เช่นใน FastAPI) → ใช้ run_until_complete
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_price_text(symbol, vs))

class _NoopResolver:
    async def refresh(self, force: bool = False) -> bool:
        return True

resolver = _NoopResolver()
