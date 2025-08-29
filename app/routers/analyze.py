# =============================================================================
# LAYER A) OVERVIEW (FastAPI Router: On-demand Analysis)
# -----------------------------------------------------------------------------
# Endpoint หลัก: /analyze/analyze   (prefix="/analyze")
# Alias: /analyze/wave, /analyze/sample, /analyze/sample-4h, /analyze/sample-1h
# - mode="text"     -> คืนข้อความสรุป (พร้อมส่ง LINE ได้)
# - mode="payload"  -> คืน payload เต็ม (percent/levels/entry/sl/tp/notes)
# =============================================================================

from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter, Query, HTTPException

from app.services.wave_service import analyze_wave, build_brief_message

router = APIRouter(tags=["analyze"])

_VALID_TF = {"1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W"}


def _norm_symbol(sym: str) -> str:
    s = (sym or "").strip().upper()
    s = s.replace(":", "/").replace("-", "/")
    parts = [p for p in s.split("/") if p]
    return f"{parts[0]}{parts[1]}" if len(parts) == 2 else s


def _norm_tf(tf: str) -> str:
    return (tf or "").strip().upper()


def _analyze_core(symbol: str, tf: str, mode: str, live_limit: int) -> Dict[str, Any]:
    if mode not in ("text", "payload"):
        raise HTTPException(status_code=400, detail="mode must be 'text' or 'payload'")
    sym = _norm_symbol(symbol)
    tf_u = _norm_tf(tf)
    if tf_u not in _VALID_TF:
        raise HTTPException(status_code=400, detail=f"invalid tf '{tf}'. allowed: {sorted(_VALID_TF)}")

    cfg = {"use_live": True, "live_limit": int(live_limit)}
    payload = analyze_wave(sym, tf_u, cfg=cfg)

    if mode == "text":
        return {
            "ok": True,
            "mode": "text",
            "symbol": sym,
            "tf": tf_u,
            "text": build_brief_message(payload),
        }

    return {"ok": True, "mode": "payload", "symbol": sym, "tf": tf_u, "payload": payload}


@router.get("/analyze", summary="วิเคราะห์สัญญาณแบบ on-demand")
def analyze_endpoint(
    symbol: str = Query("BTCUSDT"),
    tf: str = Query("1D"),
    mode: str = Query("text"),
    live_limit: int = Query(500),
) -> Dict[str, Any]:
    return _analyze_core(symbol, tf, mode, live_limit)


@router.get("/wave", summary="(Alias) วิเคราะห์สัญญาณ (เส้นทางเดิม)")
def analyze_wave_alias(
    symbol: str = Query("BTCUSDT"),
    tf: str = Query("1D"),
    mode: str = Query("text"),
    live_limit: int = Query(500),
) -> Dict[str, Any]:
    return _analyze_core(symbol, tf, mode, live_limit)


@router.get("/sample", summary="ตัวอย่างผลวิเคราะห์ BTCUSDT tf=1D")
def analyze_sample() -> Dict[str, Any]:
    return _analyze_core("BTCUSDT", "1D", "text", 200)


@router.get("/sample-4h", summary="ตัวอย่างผลวิเคราะห์ BTCUSDT tf=4H")
def analyze_sample_4h() -> Dict[str, Any]:
    return _analyze_core("BTCUSDT", "4H", "text", 200)


@router.get("/sample-1h", summary="ตัวอย่างผลวิเคราะห์ BTCUSDT tf=1H")
def analyze_sample_1h() -> Dict[str, Any]:
    return _analyze_core("BTCUSDT", "1H", "text", 200)
