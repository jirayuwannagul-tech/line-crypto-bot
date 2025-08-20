# app/features/replies/keyword_reply.py
"""
Layer สำหรับ mapping คีย์เวิร์ด → คำตอบ
สามารถแก้ไข / เพิ่มเติมได้ในที่เดียว
"""

from typing import Optional

# === Keyword mapping ===
KEYWORD_MAP = {
    "สวัสดี": "สวัสดี",
    "ราคา": "กรุณารอสักครู่ ระบบกำลังดึงราคาล่าสุด",
    "eth": "ETH กำลังมาแรง!",
    "btc": "BTC ตอนนี้กำลังแกว่งแรง!",
    "ช่วยเหลือ": "พิมพ์: สวัสดี, ราคา, eth, btc เพื่อดูคำตอบ",
}


def get_reply(text: str) -> Optional[str]:
    """
    ถ้าเจอคีย์เวิร์ดที่ match → ส่งข้อความตอบกลับ
    ถ้าไม่เจอ → return None
    """
    if not text:
        return None

    normalized = text.strip().lower()
    for key, reply in KEYWORD_MAP.items():
        if normalized == key.lower():
            return reply
    return None
