# app/routers/chat.py
from fastapi import APIRouter, Body
from pydantic import BaseModel
from app.utils.crypto_price import get_price_text

router = APIRouter()

class ChatMessage(BaseModel):
    message: dict

@router.post("/chat", summary="Chat endpoint")
async def chat_endpoint(payload: ChatMessage):
    text = str(payload.message.get("text", "")).strip().lower()

    # รองรับ: "ราคา BTC" / "ราคา ETH"
    if text.startswith("ราคา "):
        symbol = text.replace("ราคา", "", 1).strip().upper()
        reply = await get_price_text(symbol)
        return {"reply": reply}

    # ฟอลแบ็ค
    return {"reply": "พิมพ์: ราคา BTC | ราคา ETH | ราคา SOL"}
