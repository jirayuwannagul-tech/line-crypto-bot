from app.services import signal_service

def test_fetch_price_from_binance():
    price = signal_service.fetch_price("BTC/USDT")
    assert price is not None, "ควรได้ราคา ไม่ใช่ None"
    assert isinstance(price, (int, float)), "ควรเป็นตัวเลข"
    print("BTC/USDT =", price)

def test_fetch_price_text_from_binance():
    text = signal_service.fetch_price_text("BTC/USDT")
    assert isinstance(text, str), "ควรเป็น string"
    assert "BTC/USDT" in text
    print(text)
