# scripts/send_line_message.py
from __future__ import annotations
import os, sys
from dotenv import load_dotenv
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    PushMessageRequest, TextMessage as LineTextMessage
)

def env_or_fail(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"❌ ENV {key} ไม่ถูกตั้งค่า (เพิ่มใน .env หรือ export ก่อนรัน)", file=sys.stderr)
        sys.exit(1)
    return val

def send_message(text: str):
    load_dotenv()  # โหลดค่าจาก .env
    token = env_or_fail("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = env_or_fail("LINE_USER_ID")

    # ทดสอบโทเคนแบบเร็ว
    if token.startswith("<") or " " in token:
        print("❌ โทเคนผิดรูปแบบ (อย่าใส่ < > หรือช่องว่าง)", file=sys.stderr)
        sys.exit(1)

    config = Configuration(access_token=token)
    with ApiClient(config) as api_client:
        api = MessagingApi(api_client)
        api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[LineTextMessage(text=text)]
            )
        )
    print("✅ Sent:", text)

if __name__ == "__main__":
    msg = "🔔 Test message from VS Code terminal!"
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
    send_message(msg)
