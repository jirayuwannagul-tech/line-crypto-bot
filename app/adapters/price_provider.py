# app/adapters/price_provider.py
from app.utils import crypto_price

def get_price(symbol: str) -> float:
    """Wrapper คืนค่า float จาก utils.crypto_price"""
    price = crypto_price.get_price(symbol)
    return float(price)
