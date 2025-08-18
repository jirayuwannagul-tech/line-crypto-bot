# app/routers/line_webhook.py
import json
import logging
from fastapi import APIRouter, Header, HTTPException, Request

from app.utils.settings import settings
from app.adapters.line.client import verify_signature, reply_message
from app.utils.crypto_price import get_price_text

router = APIRouter()
logger = logging.getLogger(__name__)

# เหรียญที่รองรับ
SUPPORTED = {"BTC", "ETH", "SOL", "ETC", "ARB", "HBAR", "ADA", "DOGE", "SAND"}
GREETINGS = {"สวัสดี", "ดีดี", "ดีจ้า"}

@router.get("/webhook")
def webhook_verify():
    return {"status": "ok"}

@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
):
    # คอนฟิกจำเป็น
    settings.validate_line()

    # raw body
    body = await request.body()

    # ต้องมีลายเซ็น
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature")

    # ตรวจลายเซ็น
    if not verify_signature(settings.LINE_CHANNEL_SECRET, body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # แปลง JSON
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # วนอ่าน events
    events = data.get("events", [])
    for ev in events:
        if ev.get("type") == "message" and ev.get("message", {}).get("type") == "text":
            reply_token = ev.get("replyToken")
            text = (ev.get("message", {}).get("text") or "").strip()
            if not reply_token:
                continue

            s = text.upper()

            # --- ราคาคริปโต ---
            if s in SUPPORTED:
                try:
                    msg = await get_price_text(s)  # Binance → fallback CoinGecko
                    await reply_message(reply_token, [{"type": "text", "text": msg}])
                except Exception as e:
                    logger.exception("price fetch failed: %s", e)
                    await reply_message(
                        reply_token,
                        [{"type": "text", "text": f"ดึงราคา {s} ไม่สำเร็จ ลองใหม่ครับ 🙏"}],
                    )
                continue

            # --- คำทักทาย ---
            if text in GREETINGS:
                await reply_message(reply_token, [{"type": "text", "text": "สวัสดีครับ 🙏"}])
                continue

            # --- ตอบรับค่าอื่น ๆ ---
            await reply_message(reply_token, [{"type": "text", "text": f"คุณว่า: {text}"}])

    return {"status": "ok", "events": len(events)}
