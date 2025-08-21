"""
Layer สำหรับ mapping คีย์เวิร์ด → คำตอบ
- KEYWORD_MAP  : เก็บ mapping คีย์เวิร์ดแบบ fix เช่น "สวัสดี" → "ทักควยไรวะ 🤔"
- get_reply()  : ถ้าข้อความตรงกับ key ใน KEYWORD_MAP → ส่งข้อความตอบกลับ
- parse_price_command() : ตรวจจับคำสั่ง "ราคา XXX" / "price XXX" → คืน symbol เช่น BTCUSDT
"""

from typing import Optional
import re

# === Keyword mapping (ข้อความโต้ตอบทั่วไป) ===
KEYWORD_MAP = {
    "ทดสอบแจ้งเตือน": (
        "🧪 MOCK ALERT\n"
        "สัญญาณ: LONG 60% / SHORT 40%\n"
        "คู่: BTCUSDT | TF: 1H\n"
        "Entry: 59,000\n"
        "TP1: 59,500 | TP2: 60,200\n"
        "SL: 58,500\n"
        "หมายเหตุ: ข้อมูลทดสอบ ไม่ใช่สัญญาณจริง"
    ),
    "mock": (
        "🧪 MOCK ALERT\n"
        "Signal: LONG 60% / SHORT 40%\n"
        "Pair: BTCUSDT | TF: 1H\n"
        "Entry: 59,000 | TP1: 59,500 | TP2: 60,200 | SL: 58,500\n"
        "Note: Test data only."
    ),

    # ===== ชุด BTC/การพนันกวนๆ =====
    "btc": "BTC นี่มันคาสิโนชัด ๆ 🎰",
    "เปิดลอค": "เปิดลอคทีไร เจ๊งทุกที 😭",
    "เปิดชอท": "เปิดชอทปุ๊บ... แท่งเขียวทะลุจอ 🟢",
    "sl": "SL โดนกินเรียบร้อย... น้ำตาจะไหล 💦",
    "tp": "TP โดนเฉียด ๆ แล้วเด้งกลับ เจ็บจี๊ด 😤",
    "ติดดอย": "ดอยสูงขนาดนี้ ออกซิเจนเริ่มไม่พอแล้ว 🏔️",
    "ตกรถ": "รถคันนี้ไม่มีเบาะเสริมแล้วน้อง 🤣",
    "ตามพี่": "อย่าตามพี่เลย... พี่เองก็ติดดอยอยู่ 😅",
    "เลิกเทรด": "เลิกไม่ได้หรอก มันคือความบันเทิง 🎢",
    "เจ๊ง": "เจ๊งอีกแล้ว... ฝากตังค์เพิ่มได้ปะ 💸",
    "แตกพอร์ต": "พอร์ตแตก... แต่ใจยังไม่แตก (มั้ง) 💔",
    "ลาก่อน btc": "ลาก่อน BTC... ขอกลับไปขายข้าวมันไก่ละ 🍗",
    "ฟลอร์": "ลงแรงกว่านี้ก็ทะลุใต้ถุนบ้านแล้ว 🕳️",
    "บิน": "บินทีไร ตกรถทุกที ✈️",
    "เข้าไม่ทัน": "เข้าไม่ทันก็ยืนมองกราฟอย่างเดียวละกัน 👀",
    "แทงสวน": "แทงสวนทีไร โดนเหยียบจมดินทุกที 🤯",
    
    
}

def get_reply(text: str) -> Optional[str]:
    """
    Mapping ข้อความ → คำตอบ (ตาม KEYWORD_MAP)
    ถ้าเจอ key ตรง → return ข้อความตอบ
    ถ้าไม่เจอ → return None
    """
    if not text:
        return None
    normalized = text.strip().lower()
    for key, reply in KEYWORD_MAP.items():
        if normalized == key.lower():
            return reply
    return None

# === ฟังก์ชันเสริม: ตรวจจับคำสั่งขอราคา ===
_PRICE_CMD = re.compile(r'^(?:ราคา|price)\s*([A-Za-z]{3,10})(?:/USDT|USDT)?$', re.IGNORECASE)

def parse_price_command(text: str) -> Optional[str]:
    """
    ตรวจข้อความ ถ้า match pattern 'ราคา XXX' หรือ 'price XXX'
    → return symbol เป็น XXXUSDT
    เช่น:
      'ราคา BTC' → 'BTCUSDT'
      'price eth' → 'ETHUSDT'
      'ราคา BTCUSDT' → 'BTCUSDT'
    ถ้าไม่ match → return None
    """
    if not text:
        return None
    m = _PRICE_CMD.search(text.strip())
    if not m:
        return None
    base = m.group(1).upper()
    return base if base.endswith("USDT") else f"{base}USDT"
# --- MOCK analysis command parser (วางเพิ่มท้ายไฟล์) ---
import re as _re

_ANALYZE_MOCK = _re.compile(r'^(?:mock|วิเคราะห์\s*mock)\s*$', _re.IGNORECASE)

def parse_analysis_mock(text: str) -> bool:
    """
    คืน True ถ้าผู้ใช้พิมพ์ 'mock' หรือ 'วิเคราะห์ mock'
    ใช้สำหรับสั่งให้บอทตอบผลวิเคราะห์จำลอง (ไม่ใช้ราคา API จริง)
    """
    if not text:
        return False
    return _ANALYZE_MOCK.search(text.strip()) is not None

