# app/routers/health.py
from __future__ import annotations
from fastapi import APIRouter
import os
import requests

router = APIRouter()

@router.get("/health", summary="Health check")
def health():
    return {
        "ok": True,
        "env": {
            "REALTIME": os.getenv("REALTIME", ""),
            "PROVIDERS": os.getenv("PROVIDERS", "binance"),
        },
    }

@router.get("/health/ping-binance", summary="ตรวจการเชื่อมต่อไป Binance REST")
def ping_binance():
    try:
        r = requests.get("https://api.binance.com/api/v3/time", timeout=8)
        ctype = r.headers.get("content-type", "")
        body = r.json() if ctype.startswith("application/json") else r.text[:200]
        return {"ok": r.status_code == 200, "status": r.status_code, "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/health/ping-okx", summary="ตรวจการเชื่อมต่อไป OKX REST")
def ping_okx():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/time", timeout=8)
        ctype = r.headers.get("content-type", "")
        body = r.json() if ctype.startswith("application/json") else r.text[:200]
        return {"ok": r.status_code == 200, "status": r.status_code, "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}
