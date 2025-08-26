# =============================================================================
# app/main.py
# =============================================================================
# Entry point ของ FastAPI app
# - แยก Layer: Config, Lifespan, Routers, Background Tasks
# - ใช้ lifespan แทน @app.on_event
# =============================================================================

from __future__ import annotations

import os
import asyncio
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI

# ---- Utils & Settings ----
from app.utils.logging_tools import setup_logging
from app.utils.settings import settings
from app.utils.crypto_price import resolver  # no-op resolver

# ---- Routers ----
from app.routers.health import router as health_router
from app.routers.chat import router as chat_router
from app.routers.line_webhook import router as line_router
from app.routers.analyze import router as analyze_router

# ---- Features: Price Watch Alerts ----
from app.features.alerts.price_reach import run_loop  # background watcher
from app.adapters.price_provider import get_price     # ฟังก์ชันดึงราคาปัจจุบัน

# ---- LINE Messaging API (Push) ----
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

def get_line_push_fn(token: str):
    """
    คืน push function สำหรับส่งข้อความ LINE
    """
    if not token:
        return lambda *a, **k: None

    cfg = Configuration(access_token=token)

    def push_text(user_id: str, text: str) -> None:
        with ApiClient(cfg) as client:
            MessagingApi(client).push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[
                        TextMessage(
                            text=text[:4900]
                            + ("…[truncated]" if len(text) > 4900 else "")
                        )
                    ],
                )
            )
    return push_text


async def run_price_watcher(token: str):
    """
    Start background watcher loop:
    - monitor price
    - call LINE push เมื่อราคาแตะ entry
    """
    push_text = get_line_push_fn(token)

    async def _on_hit(uid: str, sym: str, price: float, entry: float):
        msg = (
            f"🔔 ราคาแตะ {sym}\n"
            f"• Price: {price:,.2f}\n"
            f"• Entry: {entry:,.2f}"
        )
        try:
            push_text(uid, msg)
        except Exception:
            # กันล้ม loop ทั้งชุด
            pass

    return await run_loop(get_price, _on_hit, interval_sec=15)


# =============================================================================
# LIFESPAN (startup/shutdown)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # === startup ===
    await resolver.refresh(force=True)  # warmup cache

    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    task: Optional[asyncio.Task] = None

    if token:
        # run watcher in background
        task = asyncio.create_task(run_price_watcher(token))

    try:
        yield
    finally:
        # === shutdown ===
        if task and not task.done():
            task.cancel()
            try:
                await task
            except Exception:
                pass


# =============================================================================
# FACTORY
# =============================================================================

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Register routers
    app.include_router(health_router)                  # /health
    app.include_router(chat_router)                    # /chat
    app.include_router(line_router, prefix="/line")    # /line/webhook
    app.include_router(analyze_router, prefix="/analyze")  # /analyze/*

    return app


# =============================================================================
# APP INSTANCE
# =============================================================================

app = create_app()


# =============================================================================
# EXTRA ROUTES
# =============================================================================

@app.get("/")
def index():
    """
    Root endpoint แสดงว่า API online
    """
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
