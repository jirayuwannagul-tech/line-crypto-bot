# app/main.py
from fastapi import FastAPI

# ✅ ใช้ logging_tools แทน logging.py
from app.utils.logging_tools import setup_logging
from app.utils.settings import settings
from app.utils.crypto_price import resolver  # warm-up resolver

# ✅ อ้างอิง router ให้ตรงไฟล์จริงในโฟลเดอร์ routers
from app.routers.health import router as health_router
from app.routers.chat import router as chat_router
from app.routers.line_webhook import router as line_router  # ใช้ไฟล์ line_webhook.py

def create_app() -> FastAPI:
    setup_logging()  # ตั้งค่า logging
    app = FastAPI(title=settings.APP_NAME, version="0.1.0")

    # รวมเส้นทาง
    app.include_router(health_router)               # /health
    app.include_router(chat_router)                 # /chat
    app.include_router(line_router, prefix="/line") # /line/webhook

    return app

app = create_app()

# อุ่นเครื่อง resolver ตอนสตาร์ท
@app.on_event("startup")
async def warmup():
    await resolver.refresh(force=True)

@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": ["/health", "/docs", "/chat (POST)"]
    }
