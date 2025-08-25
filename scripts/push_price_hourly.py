# scripts/push_price_hourly.py
import os
from app.services.price_provider_binance import BinancePriceProvider
from app.services.message_templates import build_price_message
from app.services.notifier_line import LineNotifier

def main():
    symbol = os.environ.get("PRICE_SYMBOL", "BTCUSDT")
    quote  = os.environ.get("QUOTE_ASSET", "USDT")

    # 1) ดึงราคาจาก Binance
    price = BinancePriceProvider().get_last_price(symbol)

    # 2) สร้างข้อความ
    msg = build_price_message(symbol, price, quote)

    # 3) ส่งเข้า LINE
    notifier = LineNotifier()
    to_id = notifier.push_text(msg)

    print(f"✅ ส่งเข้า LINE ({to_id}): {msg}")

if __name__ == "__main__":
    main()
