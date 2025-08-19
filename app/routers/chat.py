# app/routers/chat.py
# =============================================================================
# LAYER: ROUTER
#   - API endpoint สำหรับทดสอบเรียก SignalEngine
#   - ผู้ใช้สามารถส่ง symbol → engine → ได้สัญญาณตอบกลับ
# =============================================================================

from fastapi import APIRouter, Query
from typing import Optional
from app.services.signal_engine import SignalEngineService
from app.utils.crypto_price import fetch_ohlcv
from app.schemas.signal import SignalResponse

router = APIRouter(prefix="/chat", tags=["chat"])
service = SignalEngineService()


@router.get("/signal", response_model=SignalResponse)
async def get_signal(
    symbol: str = Query(..., description="Crypto symbol เช่น BTC, ETH"),
    use_ai: bool = Query(False, description="เปิดใช้ AI วิเคราะห์เพิ่มหรือไม่"),
):
    """
    ดึงข้อมูล OHLCV → ส่งเข้า SignalEngine → คืนผลลัพธ์สัญญาณ
    """
    df = await fetch_ohlcv(symbol)
    result = await service.analyze_symbol(symbol, ohlcv=df, use_ai=use_ai)
    return result
