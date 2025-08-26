from dotenv import load_dotenv
import os
import requests
import json

# โหลดค่าจาก .env
load_dotenv(dotenv_path=".env")
TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
TO = os.getenv("LINE_USER_ID")

if not TOKEN or not TO:
    raise ValueError("Missing LINE credentials. ตรวจสอบไฟล์ .env")

# โหลดผลวิเคราะห์จากไฟล์ JSON ที่สร้างไว้
with open("output/analyze_result.json", encoding="utf-8") as f:
    data = json.load(f)

symbol = data["symbol"]
tf = data["tf"]
last = data["last"]["close"]
ema50 = data["levels"]["ema50"]
ema200 = data["levels"]["ema200"]
percent = data["percent"]
tp = data["risk"]["tp"]
sl = data["risk"]["sl"]

msg = (
    f"{symbol} ({tf})\n"
    f"ราคา: {last:,.2f}\n"
    f"โมเมนตัม: ขึ้น {percent['up']}% | ลง {percent['down']}% | ข้าง {percent['side']}%\n"
    f"EMA50/200: {ema50:,.2f}/{ema200:,.2f}\n"
    f"TP: {tp[0]:,.2f}/{tp[1]:,.2f}/{tp[2]:,.2f} | SL: {sl:,.2f}"
)

# ส่งไป LINE Messaging API
url = "https://api.line.me/v2/bot/message/push"
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}
payload = {
    "to": TO,
    "messages": [{"type": "text", "text": msg}]
}

resp = requests.post(url, headers=headers, json=payload)
print("Status:", resp.status_code, resp.text)
