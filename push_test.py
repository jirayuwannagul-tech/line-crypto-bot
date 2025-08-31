import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
user_id = os.getenv("LINE_USER_ID")

url = "https://api.line.me/v2/bot/message/push"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "to": user_id,
    "messages": [{"type": "text", "text": "สวัสดีครับ! ทดสอบส่งจาก Python ✅"}]
}

r = requests.post(url, headers=headers, json=data)
print("Status:", r.status_code)
print("Response:", r.text)
