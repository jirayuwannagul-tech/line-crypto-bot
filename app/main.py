# =============================================================================\n# app/main.py\n# =============================================================================\n# Entry point ของ FastAPI app\n# - แยก Layer: Config, Lifespan, Routers, Background Tasks\n# - ใช้ lifespan แทน @app.on_event\n# =============================================================================\n\nfrom __future__ import annotations\n\nimport os\nimport asyncio\nfrom typing import Optional\nfrom contextlib import asynccontextmanager\n\nfrom fastapi import FastAPI\n\n# ---- Utils & Settings ----\nfrom app.utils.logging_tools import setup_logging\nfrom app.utils.settings import settings\nfrom app.utils.crypto_price import resolver  # no-op resolver\n\n# ---- Routers ----\nfrom app.routers.health import router as health_router\nfrom app.routers.chat import router as chat_router\nfrom app.routers.line_webhook import router as line_router\nfrom app.routers.analyze import router as analyze_router\n\n# ---- Features: Price Watch Alerts ----\nfrom app.features.alerts.price_reach import run_loop  # background watcher\nfrom app.adapters.price_provider import get_price     # ฟังก์ชันดึงราคาปัจจุบัน\n\n# ---- LINE Messaging API (Push) ----\nfrom linebot.v3.messaging import (\n    Configuration,\n    ApiClient,\n    MessagingApi,\n    PushMessageRequest,\n    TextMessage,\n)\n\n\n# =============================================================================\n# BACKGROUND TASKS\n# =============================================================================\n\ndef get_line_push_fn(token: str):\n    """\n    คืน push function สำหรับส่งข้อความ LINE\n    """\n    if not token:\n        return lambda *a, **k: None\n\n    cfg = Configuration(access_token=token)\n\n    def push_text(user_id: str, text: str) -> None:\n        with ApiClient(cfg) as client:\n            MessagingApi(client).push_message(\n                PushMessageRequest(\n                    to=user_id,\n                    messages=[\n                        TextMessage(\n                            text=text[:4900]\n                            + ("…[truncated]" if len(text) > 4900 else "")\n                        )\n                    ],\n                )\n            )\n    return push_text\n\n\nasync def run_price_watcher(token: str):\n    """\n    Start background watcher loop:\n    - monitor price\n    - call LINE push เมื่อราคาแตะ entry\n    """\n    push_text = get_line_push_fn(token)\n\n    async def _on_hit(uid: str, sym: str, price: float, entry: float):\n        msg = (\n            f"🔔 ราคาแตะ {sym}\n"\n            f"• Price: {price:,.2f}\n"\n            f"• Entry: {entry:,.2f}"\n        )\n        try:\n            push_text(uid, msg)\n        except Exception:\n            # กันล้ม loop ทั้งชุด\n            pass\n\n    return await run_loop(get_price, _on_hit, interval_sec=15)\n\n\n# =============================================================================\n# LIFESPAN (startup/shutdown)\n# =============================================================================\n\n@asynccontextmanager\nasync def lifespan(app):\n    # simplified lifespan: no warmup to _Resolver\n    yield\n\n    app = FastAPI(\n        title=settings.APP_NAME,\n        version="0.1.0",\n        docs_url="/docs",\n        redoc_url="/redoc",\n        openapi_url="/openapi.json",\n        lifespan=lifespan,\n    )\n\n    # Register routers\n    app.include_router(health_router)                  # /health\n    app.include_router(chat_router)                    # /chat\n    app.include_router(line_router, prefix="/line")    # /line/webhook\n    app.include_router(analyze_router, prefix="/analyze")  # /analyze/*\n\n    return app\n\n\n# =============================================================================\n# APP INSTANCE\n# =============================================================================\n\napp = create_app()\n\n\n# =============================================================================\n# EXTRA ROUTES\n# =============================================================================\n\n@app.get("/")\ndef index():\n    """\n    Root endpoint แสดงว่า API online\n    """\n    return {\n        "message": "Line Crypto Bot API is running.",\n        "try": [\n            "/health",\n            "/docs",\n            "/chat (POST)",\n            "/line/webhook (POST)",\n            "/analyze/sample",\n        ],\n    }\n

# ===== patched minimal lifespan & factory (appended) =====
try:
    from fastapi import FastAPI
except Exception as _e:
    raise

# lifespan แบบเรียบง่าย (ไม่ทำ warmup)
async def lifespan(app):
    yield

def create_app():
    app = FastAPI(lifespan=lifespan)
    # รวม router แบบปลอดภัย
    try:
        from app.routers import analyze as _analyze
        app.include_router(_analyze.router)
    except Exception as _:
        pass
    try:
        from app.routers import health as _health
        app.include_router(_health.router)
    except Exception as _:
        pass
    try:
        from app.routers import chat as _chat
        app.include_router(_chat.router)
    except Exception as _:
        pass
    try:
        from app.routers import line as _line
        app.include_router(_line.router)
    except Exception as _:
        pass
    try:
        from app.routers import line_webhook as _hook
        app.include_router(_hook.router)
    except Exception as _:
        pass
    return app
# ===== end patched block =====
