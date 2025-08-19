# app/adapters/delivery_line.py
# =============================================================================
# LINE Delivery Adapter (ready-to-use, SDK-optional)
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional, Union, List

# ---- Import schemas แบบปลอดภัยต่อ Pylance ---------------------------------
try:
    from app.schemas.signal import SignalResponse, IndicatorScore  # type: ignore
except Exception:  # pragma: no cover
    # สร้าง "ชนิด" ปลอมเพื่อใช้ใน type annotations (จะไม่พังเวลาไม่มี schemas จริง)
    class SignalResponse:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...
        def dict(self) -> Dict[str, Any]: return {}
        def model_dump(self) -> Dict[str, Any]: return {}

    class IndicatorScore:  # type: ignore
        name: str
        value: float
        weight: Optional[float]

# =============================================================================
# Formatting
# =============================================================================

_EMOJI: Dict[str, str] = {
    "BUY": "🟢",
    "SELL": "🔴",
    "HOLD": "🟡",
    "WAIT": "🟡",
    "AI_ON": "🤖",
    "AI_OFF": "📊",
    "BULLET": "•",
}

def _coerce_signal_dict(signal: Union[SignalResponse, Dict[str, Any]]) -> Dict[str, Any]:
    if hasattr(signal, "model_dump"):
        return signal.model_dump()  # Pydantic v2
    if hasattr(signal, "dict"):
        return signal.dict()  # Pydantic v1
    if isinstance(signal, dict):
        return signal
    # fallback
    return {
        "symbol": str(signal),
        "signal": "HOLD",
        "confidence": 0.0,
        "reason": "invalid_signal_type",
        "indicators": None,
        "ai_used": False,
    }

def _format_indicator_lines(indicators: Optional[List[IndicatorScore]]) -> str:
    if not indicators:
        return ""
    parts: List[str] = []
    for itm in indicators[:6]:
        try:
            name = getattr(itm, "name", None) or (itm.get("name") if isinstance(itm, dict) else None)
            value = getattr(itm, "value", None) or (itm.get("value") if isinstance(itm, dict) else None)
            weight = getattr(itm, "weight", None) or (itm.get("weight") if isinstance(itm, dict) else None)
            if name is None or value is None:
                continue
            if weight is not None:
                parts.append(f"{_EMOJI['BULLET']} {name}: {float(value):.3f} (w {float(weight):.2f})")
            else:
                parts.append(f"{_EMOJI['BULLET']} {name}: {float(value):.3f}")
        except Exception:
            continue
    return "\n".join(parts)

def format_signal_message(signal: Union[SignalResponse, Dict[str, Any]]) -> str:
    s = _coerce_signal_dict(signal)
    sym = s.get("symbol", "N/A")
    sig = str(s.get("signal", "HOLD")).upper()
    conf = float(s.get("confidence", 0.0))
    reason = s.get("reason", None)
    ai_used = bool(s.get("ai_used", False))
    indicators = s.get("indicators", None)

    emoji = _EMOJI.get(sig, "🟡")
    ai_flag = _EMOJI["AI_ON"] if ai_used else _EMOJI["AI_OFF"]

    header = f"{emoji} {sym} → {sig}"
    meta = f"ความมั่นใจ: {conf:.2f}  {ai_flag}"
    body = _format_indicator_lines(indicators)

    lines: List[str] = [header, meta]
    if reason:
        lines.append(f"เหตุผล: {reason}")
    if body:
        lines.append(body)

    return "\n".join(lines)

# =============================================================================
# Delivery
# =============================================================================

def deliver_signal_reply(
    reply_token: str,
    signal: Union[SignalResponse, Dict[str, Any]],
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    ส่งข้อความตอบกลับไปยัง LINE (reply message)
    """
    text = format_signal_message(signal)

    if client is not None:
        try:
            TextMsg = None
            try:
                from linebot.models import TextSendMessage  # type: ignore
                TextMsg = TextSendMessage
            except Exception:
                TextMsg = None

            if TextMsg is not None and hasattr(client, "reply_message"):
                client.reply_message(reply_token, TextMsg(text=text))  # type: ignore
            elif hasattr(client, "reply_message"):
                client.reply_message(reply_token, {"type": "text", "text": text})  # type: ignore
            else:
                return {"mode": "dry-run", "reply_token": reply_token, "text": text}

            return {"mode": "sent", "reply_token": reply_token, "text": text}
        except Exception as e:
            return {"mode": "error", "reply_token": reply_token, "text": text, "error": str(e)}

    return {"mode": "dry-run", "reply_token": reply_token, "text": text}
