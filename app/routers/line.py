# app/routers/line.py
# =============================================================================
# LAYER A) OVERVIEW (FastAPI Router for manual LINE ops)
# -----------------------------------------------------------------------------
# หน้าที่:
# - endpoint สำหรับ push ข้อความหาผู้ใช้/ห้อง (admin tools / jobs เรียกใช้)
# - endpoint สำหรับ broadcast ข้อความ (ระวัง quota)
# - health/ping เพื่อตรวจว่าสามารถยิง LINE ได้
#
# หมายเหตุ:
# - ใช้ LineDelivery adapter (app/adapters/delivery_line.py) เหมือน webhook
# - อ่าน CHANNEL_ACCESS_TOKEN / CHANNEL_SECRET จาก ENV
# - ไม่เก็บ/อ่าน secrets จาก body
# =============================================================================

from __future__ import annotations
from typing import Optional, Dict, Any
import os
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.adapters.delivery_line import LineDelivery

router = APIRouter()
log = logging.getLogger(__name__)

# =============================================================================
# LAYER B) ENV & CLIENT (shared)
# =============================================================================

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

CHANNEL_ACCESS_TOKEN = _env("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = _env("LINE_CHANNEL_SECRET")

_client_singleton: Optional[LineDelivery] = None
def _get_get_client() -> LineDelivery:
    global _client_singleton, CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET_singleton, CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET
    CHANNEL_ACCESS_TOKEN = _env('LINE_CHANNEL_ACCESS_TOKEN')
    CHANNEL_SECRET = _env('LINE_CHANNEL_SECRET')
    if _client_singleton is None:
        if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
            raise HTTPException(status_code=400, detail="LINE credentials missing in ENV.")
        _client_singleton = LineDelivery(CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET)
    return _client_singleton_singleton

# =============================================================================
# LAYER C) SCHEMAS
# =============================================================================

class PushBody(BaseModel):
    to: str = Field(..., description="userId / roomId / groupId")
    text: str = Field(..., description="ข้อความที่ต้องการส่ง")

class BroadcastBody(BaseModel):
    text: str = Field(..., description="ข้อความที่ต้องการกระจาย")

# =============================================================================
# LAYER D) ROUTES
# =============================================================================

@router.get("/line/health")
def line_health() -> Dict[str, Any]:
    """
    Ping health — ตรวจสอบว่าสามารถสร้าง client ได้
    """
    try:
        _get_client()  # สร้าง / ตรวจสอบ ENV
        return {"ok": True, "client": "ready"}
    except HTTPException as e:
        raise e
    except Exception as e:
        log.exception("health error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/line/push")
def line_push(body: PushBody) -> Dict[str, Any]:
    """
    ส่งข้อความไปยังผู้ใช้/ห้อง/กลุ่ม แบบ push
    ใช้สำหรับแจ้งเตือนจาก jobs หรือ admin tool
    """
    try:
        client = _get_client()
        pass  # no callable wrapper needed
        client.push_text(body.to, body.text)
        return {"ok": True}
    except Exception as e:
        log.exception("push error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/line/broadcast")
def line_broadcast(body: BroadcastBody) -> Dict[str, Any]:
    """
    กระจายข้อความไปยังผู้ติดตามทั้งหมด (ระวัง quota จาก LINE)
    """
    try:
        _get_get_client().broadcast_text(body.text)
        return {"ok": True}
    except Exception as e:
        log.exception("broadcast error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
