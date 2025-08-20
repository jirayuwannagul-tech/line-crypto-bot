import logging
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv

# โหลดค่า .env เฉพาะตอนรัน local (บน Render จะอ่าน ENV เอง)
load_dotenv(dotenv_path=Path(".") / ".env")

from app.adapters.line.client import reply_message as _reply
from app.adapters.line.client import push_message as _push
from app.adapters.line.client import broadcast_message as _broadcast

logger = logging.getLogger(__name__)

def _coerce_messages(msgs: Iterable[str] | str) -> list[dict]:
    if isinstance(msgs, str):
        msgs = [msgs]
    result = []
    for s in msgs:
        text = (s or "").strip()
        if not text:
            continue
        if len(text) > 4900:  # LINE จำกัดข้อความ ~5000 ตัว
            text = text[:4900] + "\n…(truncated)"
        result.append({"type": "text", "text": text})
    return result or [{"type": "text", "text": "(empty)"}]

async def reply_text(reply_token: str, msgs: Iterable[str] | str) -> None:
    messages = _coerce_messages(msgs)
    await _reply(reply_token, messages)

async def push_text(user_id: str, msgs: Iterable[str] | str) -> None:
    messages = _coerce_messages(msgs)
    await _push(user_id, messages)

async def broadcast_text(msgs: Iterable[str] | str) -> None:
    messages = _coerce_messages(msgs)
    await _broadcast(messages)
