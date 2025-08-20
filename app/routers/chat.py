# app/routers/chat.py
from fastapi import APIRouter, Body
from pydantic import BaseModel
from app.adapters.price_provider import fetch_spot_text

router = APIRouter()

class ChatMessage(BaseModel):
    message: dict

@router.post("/chat", summary="Chat endpoint")
async def chat_endpoint(payload: ChatMessage):
    text = str(payload.message.get("text", "")).strip().lower()

    # รองรับ: "ราคา BTC" / "ราคา ETH"
    if text.startswith("ราคา "):
        symbol = text.replace("ราคา", "", 1).strip().upper()
        reply = await fetch_spot_text(symbol, "USDT")
        return {"reply": reply}

    return {"reply": "พิมพ์: ราคา BTC | ราคา ETH | ราคา SOL"}
