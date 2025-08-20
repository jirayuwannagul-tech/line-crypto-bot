# app/routers/chat.py (ตัวอย่างการเรียก)
from fastapi import APIRouter, Request
from app.utils.crypto_price import get_price_text

router = APIRouter()

@router.post("/webhook")
async def webhook_handler(req: Request):
    body = await req.json()
    text = str(body.get("message", {}).get("text", "")).strip()

    t = text.lower()
    if t.startswith("ราคา "):
        symbol = t.replace("ราคา", "", 1).strip().upper()
        reply = await get_price_text(symbol)
        # TODO: ส่ง reply ผ่าน LINE SDK/adapter ของคุณ
        return {"reply": reply}

    if t.endswith(" ราคา"):
        symbol = t.replace("ราคา", "", 1).strip().upper()
        reply = await get_price_text(symbol)
        return {"reply": reply}

    return {"reply": "พิมพ์: ราคา BTC | ราคา ETH | …"}
