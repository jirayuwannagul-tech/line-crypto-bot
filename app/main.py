# app/main.py
from fastapi import FastAPI

from app.utils.logging_tools import setup_logging
from app.utils.settings import settings
from app.utils.crypto_price import resolver  # no-op resolver
from app.routers.health import router as health_router
from app.routers.chat import router as chat_router
from app.routers.line_webhook import router as line_router
from app.routers.analyze import router as analyze_router  # ✅ เพิ่ม import

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",       # ✅ Swagger UI
        redoc_url="/redoc",     # ✅ Redoc UI
        openapi_url="/openapi.json",  # ✅ spec JSON
    )

    # รวมเส้นทาง
    app.include_router(health_router)                 # /health
    app.include_router(chat_router)                   # /chat
    app.include_router(line_router, prefix="/line")   # /line/webhook
    app.include_router(analyze_router)                # ✅ /analyze/*

    return app

app = create_app()

@app.on_event("startup")
async def warmup():
    # no-op resolver → กัน error ตอน startup
    await resolver.refresh(force=True)

@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": ["/health", "/docs", "/chat (POST)", "/line/webhook (POST)", "/analyze/sample"]
    }
