# app/routers/line_webhook.py
import json
import logging
import re
from fastapi import APIRouter, Header, HTTPException, Request

from app.utils.settings import settings
from app.adapters.line.client import verify_signature, reply_message
from app.utils.crypto_price import get_price_text

router = APIRouter()
logger = logging.getLogger(__name__)

# พิมพ์สั้น ๆ ได้เลยสำหรับเหรียญยอดฮิต (กันสแปมข้อความทั่วไป)
SUPPORTED = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "TON"}
GREETINGS = {"สวัสดี", "ดีดี", "ดีจ้า", "hello", "hi"}

@router.get("/webhook")
def webhook_verify():
    return {"status": "ok"}

@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, alias="X-Line-Signature"),
):
    # ตรวจ config ที่ต้องมี
    settings.validate_line()

    # body + signature
    body = await request.body()
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature")
    if not verify_signature(settings.LINE_CHANNEL_SECRET, body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # parse events
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    events = data.get("events", [])
    for ev in events:
        if ev.get("type") != "message":
            continue
        if ev.get("message", {}).get("type") != "text":
            continue

        reply_token = ev.get("replyToken")
        if not reply_token:
            continue

        text = (ev.get("message", {}).get("text") or "").strip()
        upper = text.upper()

        # ---------- คำสั่ง "ราคา <SYMBOL>" (รองรับทุกเหรียญ) ----------
        m = re.search(r"ราคา\s+([A-Za-z0-9._\-]+)", text, flags=re.IGNORECASE)
        if m:
            sym = m.group(1).upper()
            try:
                msg = await get_price_text(sym)      # ใช้ resolver → รองรับทุกเหรียญ
            except Exception as e:
                logger.exception("price fetch failed: %s", e)
                msg = f"ดึงราคา {sym} ไม่สำเร็จ ลองใหม่ครับ 🙏"
            await reply_message(reply_token, [{"type": "text", "text": msg}])
            continue

        # ---------- พิมพ์สั้น ๆ แค่สัญลักษณ์ (เฉพาะ whitelist) ----------
        if upper in SUPPORTED:
            try:
                msg = await get_price_text(upper)    # รองรับทุกเหรียญ (ตัวนี้ก็ใช้ได้)
            except Exception as e:
                logger.exception("price fetch failed: %s", e)
                msg = f"ดึงราคา {upper} ไม่สำเร็จ ลองใหม่ครับ 🙏"
            await reply_message(reply_token, [{"type": "text", "text": msg}])
            continue

        # ---------- ทักทาย ----------
        if text.strip().lower() in {g.lower() for g in GREETINGS}:
            await reply_message(reply_token, [{"type": "text", "text": "สวัสดีครับ 🙏"}])
            continue

        # ---------- default help ----------
        help_msg = "พิมพ์: ราคา BTC | ราคา ETH | ราคา SOL (รองรับทุกเหรียญบน CoinGecko)"
        await reply_message(reply_token, [{"type": "text", "text": help_msg}])

    return {"status": "ok", "events": len(events)}
