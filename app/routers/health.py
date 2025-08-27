from __future__ import annotations
from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/health", summary="Health check")
def health():
    return {"ok": True, "env": {"REALTIME": os.getenv("REALTIME", ""), "PROVIDERS": os.getenv("PROVIDERS", "binance")}}

@router.get("/health/ping-binance", summary="ตรวจการเชื่อมต่อไป Binance REST")
def ping_binance():
    try:
        import requests
        r = requests.get("https://api.binance.com/api/v3/time", timeout=8)
        return {"ok": r.status_code == 200, "status": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
