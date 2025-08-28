"""
LINE Delivery Adapter (requests)
- broadcast_text(message, token=None)
"""
from __future__ import annotations

import os
from typing import Dict, Any, Tuple, Optional
import requests

__all__ = ["broadcast_text"]

LINE_API_BASE = "https://api.line.me"

def _post(path: str, body: Dict[str, Any], token: str) -> Tuple[int, str]:
    url = f"{LINE_API_BASE}{path}"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        # คืน status กับข้อความสั้น ๆ
        text = resp.text if isinstance(resp.text, str) else str(resp.content)
        return resp.status_code, text
    except requests.RequestException as e:
        return 0, f"RequestsError: {e}"

def broadcast_text(message: str, token: Optional[str] = None) -> Tuple[int, str]:
    tok = (token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
    if not tok:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN missing")

    text = (message or "").strip()
    if not text:
        return 400, "empty message"
    text = text[:5000]  # ข้อจำกัด LINE

    body = {"messages": [{"type": "text", "text": text}]}
    return _post("/v2/bot/message/broadcast", body, tok)
