# app/routers/line.py
from fastapi import APIRouter, Request
from app.services.signal_service import analyze_btc

router = APIRouter()

@router.post("/webhook")
async def webhook(req: Request):
    body = await req.json()
    text = body.get("events", [{}])[0].get("message", {}).get("text", "")

    if text.strip() == "วิเคราะห์ btc":
        reply = await analyze_btc()
    else:
        reply = "พิมพ์ 'วิเคราะห์ btc' เพื่อดูสัญญาณ"

    # (ตอนนี้ mock return, จริง ๆ ต้องส่งกลับ LINE API)
    return {"reply": reply}
