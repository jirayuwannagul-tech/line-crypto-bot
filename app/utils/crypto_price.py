# app/utils/crypto_price.py
import os
import time
import asyncio
import httpx
from typing import Optional, Dict, Tuple

# ====== ENV & DEFAULTS ======
_DEFAULT_VS = os.getenv("QUOTE_ASSET", "USDT").upper()    # ตัวเงินอ้างอิง
_PROVIDER   = os.getenv("PRICE_PROVIDER", "binance").lower()  # binance|coingecko
_PRICE_TTL  = int(os.getenv("PRICE_TTL_SECONDS", "15"))   # cache ราคา (วินาที)

# ====== SIMPLE IN-MEMORY CACHE ======
_price_cache: Dict[str, Tuple[float, float]] = {}  # key -> (price, ts)

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

# ====== HTTP helper (retry/backoff) ======
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
            if status == 429 and attempt < retries - 1:
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            if status in (400, 404):
                raise
            raise
        except httpx.RequestError:
            if attempt < retries - 1:
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            raise

# ====== PROVIDERS ======
async def _get_price_binance(symbol: str, vs: str) -> Optional[float]:
    """
    Binance Public API: https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
    รองรับเฉพาะคู่ที่มีบน Binance
    """
    pair = f"{symbol.upper()}{vs.upper()}"
    url = "https://api.binance.com/api/v3/ticker/price"
    try:
        data = await _http_get_with_retry(url, params={"symbol": pair})
        return float(data["price"])
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            return None
        raise

async def _get_price_coingecko(symbol: str, vs: str) -> Optional[float]:
    """
    CoinGecko: ใช้เป็น fallback เพื่อลดโอกาสโดนลิมิต
    """
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

# ====== PUBLIC API ======
async def get_price(symbol: str, vs: str | None = None) -> Optional[float]:
    """
    คืนราคาปัจจุบันของ symbol ในหน่วย vs (default = USDT)
    """
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

# ====== Compatibility shim (ไม่ให้โค้ดเก่าพัง) ======
async def get_price_usd(symbol: str) -> Optional[float]:
    """รองรับ adapter เก่าที่เรียก get_price_usd()"""
    return await get_price(symbol, "USDT")

# ====== No-op resolver เพื่อ warm-up ตอน startup ======
class _NoopResolver:
    async def refresh(self, force: bool = False) -> bool:
        return True

resolver = _NoopResolver()

# ====== DEBUG ======
if __name__ == "__main__":
    async def _debug():
        print(await get_price_text("BTC"))
        print(await get_price_text("ETH"))
        print(await get_price_text("ADA"))
    asyncio.run(_debug())
