# app/routers/line_webhook.py
from fastapi import APIRouter, Request
from app.adapters.line.client import reply_message
from app.utils.crypto_price import get_price_text

router = APIRouter()

@router.post("/webhook")  # ✅ เหลือแค่ /webhook เพราะ main.py มี prefix="/line"
async def line_webhook(request: Request):
    body = await request.json()
    print("LINE Webhook received:", body)

    events = body.get("events", [])
    if not events:
        return {"status": "ok"}  # ✅ ตอบกลับเสมอ

    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken")

        if event_type == "message" and reply_token:
            message = event.get("message", {})
            text = message.get("text", "").strip().lower()

            if text == "btc":
                msg = await get_price_text("btc")
                await reply_message(reply_token, [{"type": "text", "text": msg}])

            elif text == "eth":
                msg = await get_price_text("eth")
                await reply_message(reply_token, [{"type": "text", "text": msg}])

            else:
                await reply_message(reply_token, [
                    {"type": "text", "text": f"คุณพิมพ์ว่า: {text}"}
                ])

    return {"status": "ok"}
