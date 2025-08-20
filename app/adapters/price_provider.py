"""
app/adapters/price_provider.py
------------------------------
เลเยอร์: adapters
หน้าที่: ให้ฟังก์ชัน get_price(symbol) คืน "ราคาปัจจุบัน (USD) แบบ float"
แนวคิด: เป็น thin wrapper เรียกใช้ util ภายใน (app.utils.crypto_price.get_price_usd)
เหตุผล: ลดการพึ่งพาไลบรารีเพิ่ม และใช้โค้ดดึงราคาที่คุณมีอยู่แล้ว
ข้อกำหนด: คืนค่าเป็น float เสมอ, ตรวจ None/ผิดรูปแบบแล้ว raise RuntimeError ชัดเจน
"""

from typing import Union  # นำเข้า Union เพื่อระบุชนิดรับเข้า/รับออกที่ยืดหยุ่น
from app.utils import crypto_price  # นำเข้าโมดูล util ที่มีฟังก์ชัน get_price_usd อยู่แล้ว


def get_price(symbol: str) -> float:
    """ดึงราคาปัจจุบันของสัญลักษณ์ (เช่น 'BTC') ในหน่วย USD แล้วคืนเป็น float
    พฤติกรรม:
      - แปลง symbol ให้เป็นตัวพิมพ์ใหญ่ (เผื่อผู้ใช้ส่งมาเป็นตัวเล็ก)
      - เรียก crypto_price.get_price_usd(symbol) ซึ่งคาดว่าจะคืนตัวเลขได้
      - แปลงเป็น float และตรวจ None/NaN
      - ถ้าไม่สามารถดึงราคาได้ให้ raise RuntimeError พร้อมข้อความอธิบาย
    """
    if not isinstance(symbol, str) or not symbol.strip():  # ตรวจสอบ symbol เบื้องต้น
        raise RuntimeError("symbol must be a non-empty string")  # โยนข้อผิดพลาดหากไม่ถูกต้อง

    sym = symbol.strip().upper()  # ทำความสะอาดและแปลงเป็นตัวพิมพ์ใหญ่
    try:
        price: Union[float, int, str, None] = crypto_price.get_price_usd(sym)  # เรียกฟังก์ชันจาก util ที่มีอยู่
    except Exception as e:  # กันทุกกรณีที่ util อาจโยนข้อผิดพลาด
        raise RuntimeError(f"failed to fetch price from crypto_price.get_price_usd('{sym}'): {e}") from e  # โยนต่อพร้อมสาเหตุ

    if price is None:  # กรณีได้ None แปลว่าดึงราคาไม่ได้
        raise RuntimeError(f"price not available for symbol '{sym}'")  # แจ้งให้ชัดเจน

    try:
        price_f = float(price)  # แปลงผลลัพธ์ให้เป็น float เสมอ
    except (TypeError, ValueError) as e:  # ถ้าแปลงไม่สำเร็จ
        raise RuntimeError(f"invalid price format for '{sym}': {price!r}") from e  # แจ้งรูปแบบข้อมูลผิด

    if price_f <= 0:  # ตรวจว่าราคาเป็นค่าบวกสมเหตุสมผล
        raise RuntimeError(f"unexpected non-positive price for '{sym}': {price_f}")  # แจ้งหากค่าผิดปกติ

    return price_f  # คืนค่าราคาแบบ float ให้ผู้เรียกใช้งาน


# ===== 🧪 คำสั่งทดสอบ =====
# 1) ทดสอบดึงราคาโดยตรง (ต้องได้ float บวก)
# python3 -c "from app.adapters.price_provider import get_price; p=get_price('BTC'); print(type(p), p); assert p>0"
#
# 2) ใช้งานร่วมกับ scheduler (dry-run 1 รอบ)
# python3 -c "from app.scheduler.runner import tick_once; import asyncio; asyncio.run(tick_once(dry_run=True))"
#
# ✅ Acceptance:
# - ข้อ 1: แสดง <class 'float'> และค่าราคา > 0 โดยไม่มี exception
# - ข้อ 2: รอบแรก log ว่า Baseline set BTC at ...; รอบถัดไปเห็น log การคำนวณ % (ไม่มี error)
