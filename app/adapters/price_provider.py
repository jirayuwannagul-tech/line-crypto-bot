from typing import Optional
from app.utils.crypto_price import get_price, get_price_text, get_price_usd

# =============================================================================
# LAYER A) เดิม (ยังคงใช้ได้อยู่)
# =============================================================================

# ใช้ใน engine (ตัวเลข)
async def fetch_spot(symbol: str, vs: str = "USDT") -> Optional[float]:
    return await get_price(symbol, vs)

# ใช้ใน LINE (ข้อความ)
async def fetch_spot_text(symbol: str, vs: str = "USDT") -> str:
    return await get_price_text(symbol, vs)

# สำหรับโค้ดเก่า
async def legacy_get_price_usd(symbol: str) -> Optional[float]:
    return await get_price_usd(symbol)

# =============================================================================
# LAYER B) ใหม่ (เชื่อม Binance API ผ่าน ccxt)
# -----------------------------------------------------------------------------
# เพิ่มฟังก์ชันใหม่โดยไม่ทับของเก่า
# =============================================================================

import ccxt

_exchange = ccxt.binance()

def get_spot_ccxt(symbol: str = "BTC/USDT") -> Optional[float]:
    """
    ดึงราคาล่าสุดจาก Binance spot ผ่าน ccxt
    synchronous function (เรียกตรง ๆ)
    """
    try:
        ticker = _exchange.fetch_ticker(symbol)
        return ticker["last"]
    except Exception as e:
        print(f"[price_provider] ccxt error: {e}")
        return None

def get_spot_text_ccxt(symbol: str = "BTC/USDT") -> str:
    """
    ดึงราคาล่าสุดจาก Binance spot (ข้อความสำหรับ LINE)
    """
    price = get_spot_ccxt(symbol)
    if price is None:
        return f"ไม่สามารถดึงราคาจาก Binance ได้ ({symbol})"
    return f"ราคาล่าสุด {symbol} = {price:,.2f} USDT"
