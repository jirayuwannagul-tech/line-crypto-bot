# app/routers/line_webhook.py
from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/line/webhook")
async def line_webhook(request: Request):
    body = await request.json()
    print("Webhook event:", body)  # log ดูก่อน
    return {"status": "ok"}  # ✅ ตอบกลับ 200 ทันที
