# app/adapters/delivery_line.py
# =============================================================================
# LINE Delivery Adapter
# รองรับทั้ง reply (ตอบกลับ user) และ push/broadcast (แจ้งเตือนอัตโนมัติ)
# =============================================================================

import os
import httpx
import logging
from dotenv import load_dotenv

# โหลดค่า environment จากไฟล์ .env (ถ้ามี)
load_dotenv()

logger = logging.getLogger(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_API_REPLY = "https://api.line.me/v2/bot/message/reply"
LINE_API_PUSH = "https://api.line.me/v2/bot/message/push"
LINE_API_BROADCAST = "https://api.line.me/v2/bot/message/broadcast"


async def reply_message(reply_token: str, text: str) -> None:
    """ส่งข้อความ reply กลับไปยัง user (ต้องมี reply_token)"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set")
        return

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_REPLY, headers=headers, json=payload)
        if resp.is_error:
            logger.error("reply_message failed: %s %s", resp.status_code, resp.text)
        else:
            logger.info("reply_message sent: %s", text)


async def push_message(user_id: str, text: str) -> None:
    """ส่งข้อความหา user เฉพาะ (ต้องรู้ user_id หรือ groupId)"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set")
        return

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_PUSH, headers=headers, json=payload)
        if resp.is_error:
            logger.error("push_message failed: %s %s", resp.status_code, resp.text)
        else:
            logger.info("push_message sent to %s: %s", user_id, text)


async def broadcast_message(text: str) -> None:
    """ส่งข้อความ broadcast ถึงทุกคนที่ติดตาม OA"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set")
        return

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_API_BROADCAST, headers=headers, json=payload)
        if resp.is_error:
            logger.error("broadcast_message failed: %s %s", resp.status_code, resp.text)
        else:
            logger.info("broadcast_message sent: %s", text)
