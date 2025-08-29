import asyncio
from app.adapters.price_provider import get_price  # sync

async def get_price_text(symbol: str, vs: str | None = None) -> str:
    """
    shim เดิม เพื่อให้โค้ด/เทสที่เรียกใช้ยังทำงานได้
    """
    sym = (symbol or "").upper()
    px = await asyncio.to_thread(get_price, sym)
    return f"{sym}/USDT last price: {px:,.2f} USDT"

__all__ = ["get_price_text"]
