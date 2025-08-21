# app/main.py
from __future__ import annotations

import os
import asyncio
from typing import Callable

from fastapi import FastAPI

from app.utils.logging_tools import setup_logging
from app.utils.settings import settings
from app.utils.crypto_price import resolver  # no-op resolver
from app.routers.health import router as health_router
from app.routers.chat import router as chat_router
from app.routers.line_webhook import router as line_router
from app.routers.analyze import router as analyze_router

# ---- NEW: price watch loop (ต้องมีไฟล์ app/features/alerts/price_reach.py ตามที่ส่งไว้ก่อนหน้า) ----
from app.features.alerts.price_reach import run_loop  # background watcher
from app.adapters.price_provider import get_price     # ฟังก์ชันดึงราคา ปัจจุบันของโปรเจกต์

# ---- NEW: LINE Push API (v3) ----
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # รวมเส้นทาง
    app.include_router(health_router)               # /health
    app.include_router(chat_router)                 # /chat
    app.include_router(line_router, prefix="/line") # /line/webhook
    app.include_router(analyze_router)              # /analyze/*

    return app


app = create_app()


@app.on_event("startup")
async def warmup_and_start_watch_loop():
    # 1) warmup (ของเดิม)
    await resolver.refresh(force=True)

    # 2) start background price-watch loop (แจ้งเตือนเมื่อแตะ entry)
    #    ต้องตั้ง LINE_CHANNEL_ACCESS_TOKEN ใน env
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        # ไม่มี token ก็ไม่ start loop เพื่อลด error ใน env dev
        return

    def push_text(user_id: str, text: str) -> None:
        cfg = Configuration(access_token=token)
        with ApiClient(cfg) as client:
            MessagingApi(client).push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=text[:4900] + ("…[truncated]" if len(text) > 4900 else ""))],
                )
            )

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

    # เริ่มลูปด้วย provider ปัจจุบันของระบบ
    asyncio.create_task(run_loop(get_price, _on_hit, interval_sec=15))


@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": ["/health", "/docs", "/chat (POST)", "/line/webhook (POST)", "/analyze/sample"],
    }
