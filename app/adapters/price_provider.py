# app/adapters/price_provider.py
from typing import Optional
from app.utils.crypto_price import get_price, get_price_text, get_price_usd

# ใช้ใน engine (ตัวเลข)
async def fetch_spot(symbol: str, vs: str = "USDT") -> Optional[float]:
    return await get_price(symbol, vs)

# ใช้ใน LINE (ข้อความ)
async def fetch_spot_text(symbol: str, vs: str = "USDT") -> str:
    return await get_price_text(symbol, vs)

# สำหรับโค้ดเก่า
async def legacy_get_price_usd(symbol: str) -> Optional[float]:
    return await get_price_usd(symbol)
