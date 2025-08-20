# app/main.py
from fastapi import FastAPI
from app.routers import chat_router, health_router, line_router
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
    app.include_router(line_router, prefix="/line")   # /line/webhook (GET/POST)

    return app

app = create_app()

# 👇 อุ่นเครื่องลิสต์เหรียญตอนสตาร์ท (ลดพังรอบแรก)
@app.on_event("startup")
async def warmup():
    await resolver.refresh(force=True)

# =========================
# LAYER: ROOT ROUTE
# =========================
@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": ["/health", "/docs", "/chat (POST)"]
    }
