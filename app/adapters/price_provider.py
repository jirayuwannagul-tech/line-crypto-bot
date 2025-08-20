# =============================================================================
# Price Provider Adapter
# ทำหน้าที่: async wrapper สำหรับดึงราคาปัจจุบันจาก crypto_price
# =============================================================================

from typing import Union
from app.utils import crypto_price  # ใช้ util ที่เขียนไว้ใน crypto_price.py


async def get_price(symbol: str) -> float:
    """
    ดึงราคาปัจจุบันของ symbol (เช่น 'BTC') ในหน่วย USD แล้วคืนเป็น float
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise RuntimeError("symbol must be a non-empty string")

    sym = symbol.strip().upper()
    try:
        raw_price: Union[float, int, str, None] = await crypto_price.get_price_usd(sym)
    except Exception as e:
        raise RuntimeError(f"failed to fetch price for '{sym}': {e}") from e

    if raw_price is None:
        raise RuntimeError(f"price not available for '{sym}'")

    try:
        price_f = float(raw_price)
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"invalid price format for '{sym}': {raw_price!r}") from e

    if price_f <= 0:
        raise RuntimeError(f"unexpected non-positive price for '{sym}': {price_f}")

    return price_f
