# app/utils/crypto_price.py
import os
import time
import asyncio
import httpx
from typing import Optional, Dict, Tuple

_DEFAULT_VS = os.getenv("QUOTE_ASSET", "USDT").upper()
_PROVIDER   = os.getenv("PRICE_PROVIDER", "binance").lower()  # binance|coingecko
_PRICE_TTL  = int(os.getenv("PRICE_TTL_SECONDS", "15"))

_price_cache: Dict[str, Tuple[float, float]] = {}

def _cache_key(symbol: str, vs: str) -> str:
    return f"{symbol.upper()}-{vs.upper()}"

def _get_cached(symbol: str, vs: str) -> Optional[float]:
    key = _cache_key(symbol, vs)
    row = _price_cache.get(key)
    if not row:
        return None
    price, ts = row
    if time.time() - ts <= _PRICE_TTL:
        return price
    return None

def _set_cache(symbol: str, vs: str, price: float) -> None:
    key = _cache_key(symbol, vs)
    _price_cache[key] = (price, time.time())

async def _http_get_with_retry(
    url: str,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 0.75,
    timeout: int = 10
):
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            # retry เฉพาะ 429
            if status == 429 and attempt < retries - 1:
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            # ส่งต่อให้ caller ตัดสินใจ (รวมถึง 451/403)
            raise
        except httpx.RequestError:
            if attempt < retries - 1:
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            raise

# ---------- Providers ----------
async def _get_price_binance(symbol: str, vs: str) -> Optional[float]:
    """
    Binance: https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
    หมายเหตุ: บาง region/IP จะโดน 451/403
    """
    pair = f"{symbol.upper()}{vs.upper()}"
    url = "https://api.binance.com/api/v3/ticker/price"
    try:
        data = await _http_get_with_retry(url, params={"symbol": pair})
        return float(data["price"])
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        # ถ้าโดน block/geo (451) หรือ forbidden (403) หรือไม่รองรับคู่ (400/404) ให้ fallback
        if status in (400, 403, 404, 451):
            return None
        # อย่างอื่นค่อยโยนต่อ
        raise

async def _get_price_coingecko(symbol: str, vs: str) -> Optional[float]:
    vs_currency = "usd" if vs.upper() in ("USD", "USDT") else vs.lower()
    SYMBOL_MAP = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "ADA": "cardano",
        "XRP": "ripple",
        "SOL": "solana",
        "DOGE": "dogecoin",
        "SAND": "the-sandbox",
    }
    coin_id = SYMBOL_MAP.get(symbol.upper())
    if not coin_id:
        return None

    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        data = await _http_get_with_retry(url, params={"ids": coin_id, "vs_currencies": vs_currency})
        price = data.get(coin_id, {}).get(vs_currency)
        return float(price) if price is not None else None
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404, 429):
            return None
        raise

# ---------- Public API ----------
async def get_price(symbol: str, vs: str | None = None) -> Optional[float]:
    vs = (vs or _DEFAULT_VS).upper()
    cached = _get_cached(symbol, vs)
    if cached is not None:
        return cached

    providers = [_PROVIDER]
    providers += ["coingecko" if _PROVIDER == "binance" else "binance"]

    price: Optional[float] = None
    for p in providers:
        if p == "binance":
            price = await _get_price_binance(symbol, vs)
        elif p == "coingecko":
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

# ---------- Compatibility shim ----------
async def get_price_usd(symbol: str) -> Optional[float]:
    return await get_price(symbol, "USDT")

class _NoopResolver:
    async def refresh(self, force: bool = False) -> bool:
        return True

resolver = _NoopResolver()

if __name__ == "__main__":
    async def _debug():
        print(await get_price_text("BTC"))
        print(await get_price_text("ETH"))
        print(await get_price_text("ADA"))
    asyncio.run(_debug())
