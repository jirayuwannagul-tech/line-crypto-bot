# ส่งข้อความไปที่ LINE (push message)
# ใช้ LINE Messaging API v3
# ENV ต้องมี: LINE_CHANNEL_ACCESS_TOKEN, LINE_TO
# ใช้: python scripts/send_line_message.py --text "ข้อความ"
# หรือ: python scripts/send_line_message.py --to <USER_ID> --text "ข้อความ"

import os
import argparse
from dotenv import load_dotenv
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage

# โหลดค่า ENV
load_dotenv()

def push_text(to: str, text: str):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("❌ ENV LINE_CHANNEL_ACCESS_TOKEN ว่าง")

    config = Configuration(access_token=token)
    with ApiClient(config) as api_client:
        api = MessagingApi(api_client)
        req = PushMessageRequest(to=to, messages=[TextMessage(text=text)])
        api.push_message(req)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--to", default=os.getenv("LINE_TO"), help="LINE UserId/GroupId/RoomId")
    p.add_argument("--text", required=True, help="ข้อความที่จะส่ง")
    args = p.parse_args()

    if not args.to:
        raise RuntimeError("❌ ต้องใส่ --to หรือกำหนด ENV LINE_TO ใน .env")

    print(f"[DEBUG] to={args.to}")
    push_text(args.to, args.text)
    print("✅ sent")
