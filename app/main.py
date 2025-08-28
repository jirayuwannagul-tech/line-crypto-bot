# app/main.py
from __future__ import annotations

# =============================================================================
# โหลด ENV จากไฟล์ .env ตั้งแต่เริ่มรันแอป
# =============================================================================
from dotenv import load_dotenv, find_dotenv
import os
env_path = find_dotenv(usecwd=True)
if not env_path or not os.path.exists(env_path):
    env_path = ".env"
load_dotenv(env_path)

from fastapi import FastAPI
from contextlib import asynccontextmanager

# ---- Routers ----
from app.routers.health import router as health_router
from app.routers.chat import router as chat_router
from app.routers.line_webhook import (
    router as line_router,
    start_news_loop,
    stop_news_loop,
)
from app.routers.analyze import router as analyze_router


# =============================================================================
# Lifespan (startup/shutdown)
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await start_news_loop()
    yield
    # shutdown
    await stop_news_loop()


# =============================================================================
# FastAPI factory
# =============================================================================
def create_app() -> FastAPI:
    app = FastAPI(
        title="Line Crypto Bot",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(line_router, prefix="/line")
    app.include_router(analyze_router, prefix="/analyze")
    return app


app = create_app()


@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": [
            "/health",
            "/docs",
            "/chat (POST)",
            "/line/webhook (POST)",
            "/analyze/sample",
        ],
    }
