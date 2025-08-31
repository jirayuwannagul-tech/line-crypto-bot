from __future__ import annotations
import os
from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException, Query
import asyncio

# ใช้ tick_once จาก runner โดยตรง (ไม่ยุ่ง logic อื่น)
from app.scheduler.runner import tick_once

router = APIRouter(prefix="/jobs", tags=["jobs"])

def _check_token(hdr: Optional[str], q: Optional[str]) -> None:
    """Auth แบบง่าย: ใช้ SCHEDULER_TOKEN ผ่าน Header: X-Internal-Token หรือ ?token="""
    expected = os.getenv("SCHEDULER_TOKEN")
    if not expected:
        return  # dev mode (ไม่ตั้ง env) = ปล่อยผ่าน
    supplied = q or hdr
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid token")

@router.get("/cron-test", summary="ใช้ Cloud Scheduler ping ทดสอบ")
async def cron_test():
    return {"ok": True, "rev": os.getenv("K_REVISION", "local")}

@router.post("/tick", summary="รันสแกนหนึ่งรอบ", description="Cloud Scheduler เรียกครั้งเดียวต่อการปลุก")
@router.get("/tick", summary="รันสแกนหนึ่งรอบ (GET)")
async def tick(
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    token: Optional[str] = None,
    symbols: Optional[str] = Query(None, description="คั่นด้วย comma เช่น BTC,ETH,SOL (ไม่ระบุ = TOP10)"),
    dry_run: bool = Query(False, description="True = แค่ log ไม่ส่ง LINE"),
):
    _check_token(x_internal_token, token)
    sym_list: Optional[List[str]] = None
    if symbols:
        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    # เรียก tick_once 1 รอบ แล้วจบ
    result = tick_once(symbols=sym_list, dry_run=dry_run)
    return {"ok": True, "ran": True, "symbols": sym_list or "TOP10", "dry_run": dry_run}
