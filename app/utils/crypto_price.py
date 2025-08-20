# app/utils/crypto_price.py
import httpx
import asyncio
import time

# ===== CACHE สำหรับเก็บผลลัพธ์ชั่วคราว =====
_coin_cache = None
_coin_cache_time = 0
_CACHE_TTL = 60 * 30  # 30 นาที

# ===== Symbol Mapping (ยกตัวอย่าง) =====
SYMBOL_MAP = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "bnb": "binancecoin",
    "ada": "cardano",
    "xrp": "ripple",
    "sol": "solana",
    "doge": "dogecoin",
}

# ===== ดึงรายชื่อเหรียญจาก CoinGecko =====
async def _fetch_all_coins():
    global _coin_cache, _coin_cache_time

    # ถ้ามี cache และยังไม่หมดอายุ → ใช้ cache
    if _coin_cache and (time.time() - _coin_cache_time < _CACHE_TTL):
        return _coin_cache

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/coins/list?include_platform=false"
            )
            r.raise_for_status()
            _coin_cache = r.json()
            _coin_cache_time = time.time()
            return _coin_cache
    except httpx.HTTPStatusError as e:
        print(f"⚠️ CoinGecko API error: {e}")
        # fallback กันพัง → ให้เฉพาะ BTC/ETH
        return [
            {"id": "bitcoin", "symbol": "btc"},
            {"id": "ethereum", "symbol": "eth"},
        ]
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")
        return [
            {"id": "bitcoin", "symbol": "btc"},
            {"id": "ethereum", "symbol": "eth"},
        ]


# ===== ดึงราคาจริงจาก CoinGecko =====
async def get_price(symbol: str) -> float | None:
    symbol = symbol.lower()

    # map symbol → id
    coin_id = SYMBOL_MAP.get(symbol)
    if not coin_id:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
            r.raise_for_status()
            data = r.json()
            return data.get(coin_id, {}).get("usd")
    except httpx.HTTPStatusError as e:
        print(f"⚠️ Price fetch error: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")
        return None


# ===== Format เป็นข้อความพร้อมใช้งาน =====
async def get_price_text(symbol: str) -> str:
    price = await get_price(symbol)
    if price is None:
        return f"❌ ไม่พบราคา {symbol.upper()}"
    return f"💰 ราคา {symbol.upper()} ล่าสุด: {price:,.2f} USD"


# ===== Debug Run =====
if __name__ == "__main__":
    async def main():
        msg = await get_price_text("btc")
        print(msg)

    asyncio.run(main())
