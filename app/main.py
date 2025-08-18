# app/main.py
from fastapi import FastAPI
from app.routers.health import router as health_router
from app.routers.chat import router as chat_router
from app.routers.line_webhook import router as line_router
from app.utils.logging import setup_logging
from app.utils.settings import settings

# =========================
# LAYER: CONFIG & LOGGING
# =========================
def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=settings.APP_NAME, version="0.1.0")

    # =========================
    # LAYER: ENGINES / SERVICES (RESERVED)
    #   - Example (later):
    #       from app.services.signal_engine import SignalEngine
    #       app.state.signal_engine = SignalEngine()
    # =========================

    # =========================
    # LAYER: MIDDLEWARE (RESERVED)
    #   - Example (later): CORS / Rate limit / Tracing
    # =========================

    # =========================
    # LAYER: ROUTERS
    # =========================
    app.include_router(health_router)                 # /health
    app.include_router(chat_router)                   # /chat
    app.include_router(line_router, prefix="/line")   # /line/webhook (GET/POST)

    return app

app = create_app()

# =========================
# LAYER: ROOT ROUTE
# =========================
@app.get("/")
def index():
    return {
        "message": "Line Crypto Bot API is running.",
        "try": ["/health", "/docs", "/chat (POST)"]
    }
