# app/routers/analyze.py
# =============================================================================
# LAYER A) OVERVIEW (FastAPI Router: On-demand Analysis)
# -----------------------------------------------------------------------------
# หน้าที่:
# - ให้ HTTP endpoint สำหรับเรียกวิเคราะห์แบบ on-demand
# - รับพารามิเตอร์: symbol, tf, profile, mode
# - mode="text"     -> คืนข้อความสรุป พร้อมใช้ส่ง LINE ต่อได้ทันที
# - mode="payload"  -> คืน payload เต็ม (entry/sl/tp/percent/levels/notes…)
# - ใช้ Service layer: app/services/signal_service.py
# =============================================================================

from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, HTTPException

from app.services.signal_service import (
    analyze_and_get_text,
    analyze_and_get_payload,
)

router = APIRouter(tags=["analyze"])

# =============================================================================
# LAYER B) INPUT / NORMALIZATION
# -----------------------------------------------------------------------------
# - ใช้ Query() เพื่อกำหนดค่าเริ่มต้น + คำอธิบายบน OpenAPI
# - profile รองรับ: baseline | cholak | chinchot (หรือโปรไฟล์ใหม่ตาม YAML)
# - รองรับสัญลักษณ์ที่คั่นด้วย ":" หรือ "/" โดยจะแปลงเป็นรูปแบบ "BASE-QUOTE"
# =============================================================================

_VALID_TF = {"1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W"}

def _norm_symbol(sym: str) -> str:
    # ตัวอย่าง: btcusdt, BTC/USDT, BTC:USDT -> BTCUSDT หรือ BTC-USDT แล้วแต่ระบบ downstream
    s = sym.strip().upper()
    s = s.replace(":", "/").replace("-", "/")
    parts = [p for p in s.split("/") if p]
    if len(parts) == 2:
        return f"{parts[0]}{parts[1]}"
    return s

def _norm_tf(tf: str) -> str:
    t = tf.strip().upper()
    return t


# =============================================================================
# LAYER C) ENDPOINTS
# -----------------------------------------------------------------------------
# /analyze            -> mode=text|payload (ดีฟอลต์ text)
# /analyze/wave       -> alias ของ /analyze (เผื่อ client เก่า)
# =============================================================================

@router.get(
    "/analyze",
    summary="วิเคราะห์สัญญาณแบบ on-demand",
    description=(
        "เรียกวิเคราะห์สัญญาณสำหรับสัญลักษณ์และ timeframe ที่กำหนด\n\n"
        "ตัวอย่าง:\n"
        "• /analyze?symbol=BTCUSDT&tf=1D&profile=baseline&mode=text\n"
        "• /analyze?symbol=ETHUSDT&tf=4H&profile=chinchot&mode=payload\n"
    ),
)
def analyze_endpoint(
    symbol: str = Query("BTCUSDT", description="เช่น BTCUSDT, ETHUSDT หรือรูปแบบ BTC/USDT"),
    tf: str = Query("1D", description="หนึ่งใน: 1M,5M,15M,30M,1H,4H,1D,1W"),
    profile: str = Query("baseline", description="baseline | cholak | chinchot (หรือโปรไฟล์ที่กำหนดใน YAML)"),
    mode: str = Query("text", description="text | payload"),
) -> Dict[str, Any]:
    if mode not in ("text", "payload"):
        raise HTTPException(status_code=400, detail="mode must be 'text' or 'payload'")

    sym = _norm_symbol(symbol)
    tf_u = _norm_tf(tf)

    if tf_u not in _VALID_TF:
        raise HTTPException(status_code=400, detail=f"invalid tf '{tf}'. allowed: {sorted(_VALID_TF)}")

    if mode == "text":
        text = analyze_and_get_text(sym, tf_u, profile=profile)
        return {
            "ok": True,
            "mode": "text",
            "symbol": sym,
            "tf": tf_u,
            "profile": profile,
            "text": text,
        }

    # mode == "payload"
    payload = analyze_and_get_payload(sym, tf_u, profile=profile)
    if not payload or not payload.get("ok", False):
        raise HTTPException(status_code=500, detail=(payload.get("error") if isinstance(payload, dict) else "analysis failed"))
    return {
        "ok": True,
        "mode": "payload",
        "symbol": sym,
        "tf": tf_u,
        "profile": profile,
        "payload": payload,
    }


@router.get(
    "/analyze/wave",
    summary="(Alias) วิเคราะห์สัญญาณแบบ on-demand (เส้นทางเดิม)",
    description="Alias ของ /analyze เพื่อรองรับ client เดิม สามารถใช้พารามิเตอร์เดียวกันทั้งหมด",
)
def analyze_wave_alias(
    symbol: str = Query("BTCUSDT", description="เช่น BTCUSDT, ETHUSDT หรือรูปแบบ BTC/USDT"),
    tf: str = Query("1D", description="หนึ่งใน: 1M,5M,15M,30M,1H,4H,1D,1W"),
    profile: str = Query("baseline", description="baseline | cholak | chinchot"),
    mode: str = Query("text", description="text | payload"),
) -> Dict[str, Any]:
    # เรียก handler หลักโดยตรง (ไม่ duplicate logic)
    return analyze_endpoint(symbol=symbol, tf=tf, profile=profile, mode=mode)
