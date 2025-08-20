# app/main.py (เพิ่ม event สำหรับ warm-up สัญลักษณ์ตอนสตาร์ท)
from fastapi import FastAPI
from app.utils.crypto_price import resolver

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # โหลดลิสต์เหรียญล่วงหน้า (ไม่บังคับ แต่ช่วยให้ตอบครั้งแรกไวขึ้น)
    await resolver.refresh(force=True)
