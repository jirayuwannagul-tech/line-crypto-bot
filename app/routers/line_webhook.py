# app/routers/line_webhook.py
from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/line/webhook")
async def line_webhook(request: Request):
    body = await request.json()
    print("LINE Webhook event:", body)  # log ดูว่าได้อะไร
    return {"status": "ok"}  # ✅ ตอบกลับ 200 ทุกครั้ง
