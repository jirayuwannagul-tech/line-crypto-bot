from fastapi import APIRouter, Request
from app.adapters.line.client import reply_message
from app.utils.crypto_price import get_price_text

router = APIRouter()

@router.post("/line/webhook")
async def line_webhook(request: Request):
    body = await request.json()
    print("LINE Webhook received:", body)

    # ✅ กรณี LINE ส่ง events: [] มา ให้ตอบ 200 OK กลับไปเลย
    events = body.get("events", [])
    if not events:
        return {"status": "ok"}

    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken")

        # ✅ กรณีข้อความเข้ามา
        if event_type == "message" and reply_token:
            message = event.get("message", {})
            text = message.get("text", "").strip().lower()

            # ถ้าพิมพ์ว่า btc → ส่งราคากลับ
            if text == "btc":
                msg = await get_price_text("btc")
                await reply_message(reply_token, [{"type": "text", "text": msg}])

            # ถ้าพิมพ์ว่า eth → ส่งราคากลับ
            elif text == "eth":
                msg = await get_price_text("eth")
                await reply_message(reply_token, [{"type": "text", "text": msg}])

            # กรณีข้อความอื่น → echo กลับ
            else:
                await reply_message(reply_token, [
                    {"type": "text", "text": f"คุณพิมพ์ว่า: {text}"}
                ])

    return {"status": "ok"}  # ✅ ต้องตอบกลับ 200 เสมอ
