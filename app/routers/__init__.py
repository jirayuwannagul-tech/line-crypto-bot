# app/routers/__init__.py
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.line_webhook import router as line_router

__all__ = ["chat_router", "health_router", "line_router"]
