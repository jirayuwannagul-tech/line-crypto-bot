import requests
from app.services.wave_service import analyze_wave, build_brief_message

# ฟังก์ชันดึงราคาปัจจุบันของ BTC จาก Binance
def get_btc_price():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    response = requests.get(url)
    data = response.json()
    return float(data['price'])

# ฟังก์ชันวิเคราะห์คลื่น Elliott
def analyze_elliott_wave(price):
    # สมมติว่า 'price' คือข้อมูลราคาปัจจุบัน
    # คุณสามารถเพิ่มการคำนวณหรือการวิเคราะห์คลื่น Elliott ที่นี่ได้
    payload = analyze_wave("BTCUSDT", "1D", cfg={"use_live": True, "live_limit": 500})
    message = build_brief_message(payload)
    return message

# ดึงราคาปัจจุบันของ BTC
btc_price = get_btc_price()
print(f"Current BTC Price: {btc_price} USD")

# ทำการวิเคราะห์คลื่น Elliott
result = analyze_elliott_wave(btc_price)
print("Elliott Wave Analysis Result:")
print(result)

