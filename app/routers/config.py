from fastapi import APIRouter

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/ping")
async def ping():
    """health check สำหรับ router config"""
    return {"status": "ok", "router": "config"}
