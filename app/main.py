from fastapi import FastAPI
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.line_router import router as line_router   # 👈 เปลี่ยนเป็น line_router.py
from app.utils.logging import setup_logging
from app.utils.settings import settings
from app.utils.crypto_price import resolver  # 👈 warm-up resolver

# =========================
# LAYER: CONFIG & LOGGING
# =========================
def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=settings.APP_NAME, version="0.1.0")

    # =========================
    # LAYER: ROUTERS
    # =========================
    app.include_router(health_router)                 # /health
    app.include_router(chat_router)                   # /chat
    app.include_router(line_router, prefix="/line")   # /line/webhook

    return app

app = create_app()

# 👇 อุ่นเครื่องลิสต์เหรียญตอนสตาร์ท (ลดพังรอบแรก)
@app.on_event("startup")
async def warmup():
    await resolver.refresh(force=True)
    settings.validate_line()   # เช็ก env ว่าตั้ง LINE token ครบ

# =========================
# LAYER: ROOT ROUTE
# =========================
@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": ["/health", "/docs", "/chat (POST)", "/line/webhook"]
    }
