# app/routers/analyze.py
# =============================================================================
# LAYER A) OVERVIEW (FastAPI Router: On-demand Analysis)
# -----------------------------------------------------------------------------
# หน้าที่:
# - ให้ HTTP endpoint สำหรับเรียกวิเคราะห์แบบ on-demand
# - รับพารามิเตอร์: symbol, tf, profile, mode
# - mode="text"  -> คืนข้อความสรุป พร้อมใช้ส่ง LINE ต่อได้ทันที
# - mode="payload" -> คืน payload เต็ม (entry/sl/tp/percent/levels/notes…)
# - ใช้ Service layer: app/services/signal_service.py
# =============================================================================

from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, HTTPException

from app.services.signal_service import (
    analyze_and_get_text,
    analyze_and_get_payload,
)

router = APIRouter()

# =============================================================================
# LAYER B) INPUT SCHEMA VIA QUERY PARAMS
# -----------------------------------------------------------------------------
# - ใช้ Query() เพื่อใส่ค่าเริ่มต้นและคำอธิบาย
# - profile รองรับ: baseline | cholak | chinchot (หรือโปรไฟล์ใหม่ที่นิยามใน YAML)
# =============================================================================

def _norm_symbol(sym: str) -> str:
    return sym.upper().replace(":", "").replace("/", "-")

@router.get("/analyze")
def analyze_endpoint(
    symbol: str = Query("BTCUSDT", description="เช่น BTCUSDT, ETHUSDT"),
    tf: str = Query("1D", description="1H/4H/1D"),
    profile: str = Query("baseline", description="baseline | cholak | chinchot"),
    mode: str = Query("text", description="text | payload"),
) -> Dict[str, Any] | str:
    """
    ตัวอย่าง:
      /analyze?symbol=BTCUSDT&tf=1D&profile=chinchot&mode=text
      /analyze?symbol=ETHUSDT&tf=4H&profile=cholak&mode=payload
    """
    if mode not in ("text", "payload"):
        raise HTTPException(status_code=400, detail="mode must be 'text' or 'payload'")

    sym = _norm_symbol(symbol)
    tf_u = tf.upper()

    if mode == "text":
        text = analyze_and_get_text(sym, tf_u, profile=profile)
        return {"ok": True, "mode": "text", "symbol": sym, "tf": tf_u, "profile": profile, "text": text}

    # payload
    payload = analyze_and_get_payload(sym, tf_u, profile=profile)
    if not payload.get("ok"):
        raise HTTPException(status_code=500, detail=payload.get("error", "analysis failed"))
    return {"ok": True, "mode": "payload", "payload": payload}
