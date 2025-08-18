# app/routers/chat.py
# ============================================
# LAYER: ROUTER (API/LINE-facing)
# ============================================
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Body
from typing import Optional, Literal, Dict, Any

# ===== IMPORTS (domain adapters) =====
from app.config.symbols import resolve_symbol, is_supported, SUPPORTED
from app.utils.crypto_price import fetch_ohlcv, fetch_spot

router = APIRouter(prefix="/chat", tags=["chat"])

# ===== SIMPLE PING =====
@router.get("/ping")
def ping() -> Dict[str, Any]:
    return {"ok": True, "service": "chat", "supported": SUPPORTED}

# ===== ENDPOINT: BASIC PRICE SUMMARY =====
@router.post("")
def chat_summary(
    payload: Dict[str, Any] = Body(
        ..., example={"symbol": "BTC", "days": 1}
    )
):
    """
    รับ symbol จากผู้ใช้ → ตรวจสอบ → ดึงราคา/กราฟขั้นต้น
    NOTE:
      - ส่วน 'วิเคราะห์สัญญาณ' จะต่อเข้ากับ services/signal_engine.py ภายหลัง (ดู MARKER ด้านล่าง)
    """
    symbol = str(payload.get("symbol", "BTC")).upper()
    days = int(payload.get("days", 1))

    if not is_supported(symbol):
        raise HTTPException(status_code=400, detail=f"Unsupported symbol: {symbol}. Supported: {', '.join(SUPPORTED)}")

    symbol_id = resolve_symbol(symbol)

    # ===== FETCH: SPOT & OHLCV =====
    try:
        spot = fetch_spot(symbol_id)  # อาจเป็น None ถ้า provider ล่ม
        df = fetch_ohlcv(symbol_id, days=days)  # DataFrame พร้อมใช้งาน
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"price provider error: {e}")

    last_price = float(df["close"].iloc[-1])

    # ============================================
    # MARKER (RESERVED): CALL SignalEngine
    #   from app.services.signal_engine import SignalEngine
    #   engine = request.app.state.signal_engine
    #   result = engine.process_ohlcv(symbol, df)
    # ============================================

    # ===== FORMAT RESPONSE (ชั่วคราว) =====
    return {
        "symbol": symbol,
        "provider_id": symbol_id,
        "spot": spot,
        "last_close": last_price,
        "rows": int(df.shape[0]),
        "note": "SignalEngine will be wired here later."
    }
