"""
app/adapters/price_provider.py
------------------------------
เลเยอร์: adapters
หน้าที่: ให้ฟังก์ชัน async get_price(symbol) คืน "ราคาปัจจุบัน (USD) แบบ float"
แนวคิด: เป็น thin async wrapper เรียกใช้ util ภายใน (app.utils.crypto_price.get_price_usd)
เหตุผล: เดิม util เป็น async (coroutine) จึงต้องปรับ provider ให้ async แล้ว await ให้ถูกต้อง
ข้อกำหนด: คืนค่าเป็น float เสมอ, ตรวจ None/ผิดรูปแบบแล้ว raise RuntimeError ชัดเจน
"""

from typing import Union  # นำเข้า Union สำหรับอธิบายชนิดค่าที่อาจรับมาได้หลายแบบ
from app.utils import crypto_price  # นำเข้าโมดูล util ที่มีฟังก์ชัน async get_price_usd อยู่แล้ว


async def get_price(symbol: str) -> float:
    """ดึงราคาปัจจุบันของสัญลักษณ์ (เช่น 'BTC') ในหน่วย USD แล้วคืนเป็น float (async)
    พฤติกรรม:
      - ตรวจสอบสตริง symbol ขั้นต้น
      - แปลง symbol เป็นตัวพิมพ์ใหญ่เพื่อความสม่ำเสมอ
      - await crypto_price.get_price_usd(symbol) (ซึ่งเป็น async) ให้ได้ผลลัพธ์ดิบ
      - แปลงเป็น float และตรวจว่าค่า > 0
      - ถ้าไม่สามารถดึงราคาได้หรือรูปแบบไม่ถูกต้องให้ raise RuntimeError
    """
    if not isinstance(symbol, str) or not symbol.strip():  # ตรวจว่า symbol เป็นสตริงไม่ว่าง
        raise RuntimeError("symbol must be a non-empty string")  # แจ้งข้อผิดพลาดหากไม่ถูกต้อง

    sym = symbol.strip().upper()  # ทำความสะอาดและแปลงสัญลักษณ์เป็นตัวพิมพ์ใหญ่
    try:
        raw_price: Union[float, int, str, None] = await crypto_price.get_price_usd(sym)  # เรียก util แบบ await เพื่อได้ตัวเลขล่าสุด
    except Exception as e:  # กันทุกกรณีที่ util อาจโยนข้อผิดพลาด
        raise RuntimeError(f"failed to fetch price from crypto_price.get_price_usd('{sym}'): {e}") from e  # โยนต่อพร้อมสาเหตุ

    if raw_price is None:  # ถ้าได้ None แสดงว่าดึงราคาไม่สำเร็จ
        raise RuntimeError(f"price not available for symbol '{sym}'")  # แจ้งให้ชัดเจนว่าราคาไม่มี

    try:
        price_f = float(raw_price)  # แปลงผลลัพธ์ให้เป็น float เสมอ
    except (TypeError, ValueError) as e:  # ถ้าแปลงไม่สำเร็จ (เช่น เป็น object แปลก ๆ)
        raise RuntimeError(f"invalid price format for '{sym}': {raw_price!r}") from e  # แจ้งรูปแบบข้อมูลผิด

    if price_f <= 0:  # ตรวจว่าราคาเป็นค่าบวกสมเหตุสมผล
        raise RuntimeError(f"unexpected non-positive price for '{sym}': {price_f}")  # แจ้งหากค่าผิดปกติ

    return price_f  # คืนค่าราคาแบบ float ให้ผู้เรียกใช้งาน


# ===== 🧪 คำสั่งทดสอบ =====
# 1) ทดสอบดึงราคาแบบ async (ต้องได้ float บวกและไม่ error)
# python3 - <<'PY'
# import asyncio
# from app.adapters.price_provider import get_price
# async def main():
#     p = await get_price('BTC')
#     print(type(p), p)
#     assert isinstance(p, float) and p > 0
# asyncio.run(main())
# PY
#
# 2) ใช้งานร่วมกับ scheduler (dry-run 1 รอบ)
# python3 -c "from app.scheduler.runner import tick_once; import asyncio; asyncio.run(tick_once(dry_run=True))"
#
# ✅ Acceptance:
# - ข้อ 1: แสดง <class 'float'> และค่าราคา > 0 โดยไม่มี exception
# - ข้อ 2: รอบแรก log ว่า Baseline set BTC at ...; รอบถัดไปเห็น log การคำนวณ % (ไม่มี error)
