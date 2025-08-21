# scripts/send_line_message.py
import os
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage as LineTextMessage,
)

# ต้องใส่ค่า 2 ตัวนี้ให้ถูกต้อง!
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "<your-access-token>")
USER_ID = os.getenv("LINE_USER_ID", "<your-user-id>")  # ใส่ userId ของคุณเอง (จาก event.source.userId)

def send_message(text: str):
    config = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    with ApiClient(config) as api_client:
        line_api = MessagingApi(api_client)
        line_api.push_message(
            PushMessageRequest(
                to=USER_ID,
                messages=[LineTextMessage(text=text)]
            )
        )
        print("✅ Sent:", text)


if __name__ == "__main__":
    # ตัวอย่าง: ส่งข้อความ test ไป LINE
    send_message("🔔 Test message from VS Code terminal!")
