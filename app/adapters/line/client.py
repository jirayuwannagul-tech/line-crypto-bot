# app/adapters/line/client.py
import os
import httpx

# โหลดค่า Secret และ Token จาก Environment Variables
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "5ff2d689dc8f9c4ac7d45a5a20ce11c3")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "mM52D20uS9a26xlYyiptXflTHGSb4Oo/y1KAJiEZb34SRxxNjICQFUaFgQevtDT9xnoOLHRevaI9g3sxhNpQlyW5Xkdhw51/jwVAVoPGhoEfc85BqWYXrtvSP1kVVD1cqZQEBM2/cdOpiWI1j2q4JAdB04t89/1O/w1cDnyilFU=")

LINE_API_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


async def reply_message(reply_token: str, messages: list):
    """
    ส่งข้อความกลับไปยังผู้ใช้ผ่าน LINE Messaging API

    :param reply_token: token ที่ LINE ส่งมาใน event
    :param messages: list ของ dict เช่น [{"type": "text", "text": "hello"}]
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    body = {
        "replyToken": reply_token,
        "messages": messages
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(LINE_API_REPLY_URL, headers=headers, json=body)

    if response.status_code != 200:
        print("❌ LINE reply error:", response.text)
    else:
        print("✅ Message sent to LINE:", body)
