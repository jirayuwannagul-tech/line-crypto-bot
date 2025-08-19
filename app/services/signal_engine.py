# app/services/signal_engine.py
# =============================================================================
# LAYER: SERVICE
#   - ตัวกลางเรียกใช้ SignalEngine (core logic)
#   - จัดรูปผลลัพธ์ให้เป็น Schema
# =============================================================================

from typing import Any, Dict, Optional
from app.engine.signal_engine import SignalEngine
from app.schemas.signal import SignalResponse


class SignalEngineService:
    def __init__(self) -> None:
        # สร้าง instance ของ core SignalEngine
        self.engine = SignalEngine()

    async def analyze_symbol(
        self,
        symbol: str,
        ohlcv: Any = None,
        use_ai: bool = False
    ) -> SignalResponse:
        """
        วิเคราะห์สัญญาณสำหรับ symbol ที่ให้มา
        :param symbol: เช่น BTC, ETH
        :param ohlcv: DataFrame OHLCV (open, high, low, close, volume)
        :param use_ai: ถ้า True จะเปิด logic AI เสริม
        """
        result: Dict[str, Any] = self.engine.process_ohlcv(symbol, df=ohlcv, use_ai=use_ai)
        return SignalResponse(**result)

    async def reset_symbol(self, symbol: str) -> None:
        """รีเซ็ต state ของสัญลักษณ์ (ล้าง position, signal ts)"""
        self.engine.reset_symbol(symbol)

    async def toggle_ai(self, enabled: bool) -> None:
        """เปิด/ปิดโหมด AI"""
        self.engine.set_ai(enabled)
