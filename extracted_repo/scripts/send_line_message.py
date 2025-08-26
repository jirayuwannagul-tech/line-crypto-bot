# ส่งข้อความไปที่ LINE (push message)
# ใช้ LINE Messaging API v3
# ENV ต้องมี: LINE_CHANNEL_ACCESS_TOKEN
# ใช้: python scripts/send_line_message.py --to <USER_ID> --text "ข้อความ"

import os
import argparse
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage

def push_text(to: str, text: str):
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("ENV LINE_CHANNEL_ACCESS_TOKEN ว่าง")

    config = Configuration(access_token=token)
    with ApiClient(config) as api_client:
        api = MessagingApi(api_client)
        req = PushMessageRequest(to=to, messages=[TextMessage(text=text)])
        api.push_message(req)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True, help="LINE UserId/GroupId/RoomId")
    p.add_argument("--text", required=True, help="ข้อความที่จะส่ง")
    args = p.parse_args()
    push_text(args.to, args.text)
    print("✅ sent")
