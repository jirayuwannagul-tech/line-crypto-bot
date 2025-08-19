# app/schemas/signal.py
# =============================================================================
# LAYER: SCHEMA
#   - Pydantic models สำหรับ response ของ SignalEngine
# =============================================================================

from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel


class PositionSchema(BaseModel):
    side: Literal["NONE", "LONG", "SHORT"]
    entry: Optional[float]
    sl: Optional[float]
    tp: Optional[float]
    opened_ts: Optional[float]


class SignalResponse(BaseModel):
    action: Literal["OPEN", "HOLD", "CLOSE", "ALERT"]
    side: Literal["NONE", "LONG", "SHORT"]
    price: Optional[float]
    sl: Optional[float]
    tp: Optional[float]
    reason: str
    analysis: Dict[str, Any]
    position: PositionSchema
