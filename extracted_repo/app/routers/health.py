# app/routers/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health", summary="Health check")
def health():
    return {"ok": True}
