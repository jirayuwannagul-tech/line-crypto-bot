"""
app/scheduler/runner.py
-----------------------
เลเยอร์: scheduler
หน้าที่: รันงาน background เพื่อตรวจราคา BTC เป็นช่วง ๆ และส่งแจ้งเตือนเมื่อเปลี่ยนแปลง ≥ threshold
ผูกกับ:
- app/settings/alerts.py            (โหลดค่าการตั้งค่า)
- app/adapters/price_provider.py    (ดึงราคาตัวเลข ถ้ามี)
- app/utils/crypto_price.py         (fallback ดึงราคาถ้า provider ไม่มีตัวเลข)
- app/features/alerts/percentage_change.py (คำนวณ % + hysteresis)
- app/utils/state_store.py          (เก็บ baseline / last_alert_ts / last_state / cooldown)
- app/adapters/delivery_line.py     (ส่งข้อความ LINE ถ้าเปิดใช้งานและไม่ dry-run)

ข้อกำหนด:
- tick_once(dry_run=False): ทำงาน 1 รอบ (ดึงราคา → ประเมิน → ตรวจ cooldown → (ถ้าไม่ dry-run) ส่ง LINE → อัปเดต state)
- run_scheduler(): วนลูปเรียก tick_once() ทุก alert_settings.poll_sec วินาที (async)
"""

import asyncio  # ใช้สำหรับทำงานแบบ async และ sleep
import logging  # ใช้ระบบล็อกเพื่อดูพฤติกรรม/ดีบัก
from typing import Optional  # ใช้ระบุชนิดข้อมูล Optional

# ===== ตั้งค่า logger พื้นฐาน =====
logger = logging.getLogger(__name__)  # สร้าง logger ตามชื่อโมดูลนี้
if not logger.handlers:  # ถ้ายังไม่มี handler (กันซ้ำเวลานำเข้า)
    logging.basicConfig(level=logging.INFO)  # ตั้งค่า logging ขั้นต่ำเป็น INFO

# ===== นำเข้า settings (threshold, poll interval, cooldown, hysteresis, enabled, symbol) =====
from app.settings.alerts import alert_settings  # โหลดค่าการตั้งค่าการแจ้งเตือนทั้งหมด

# ===== นำเข้า state/utils สำหรับเก็บสถานะและคำนวณ % =====
from app.utils.state_store import (  # ฟังก์ชันจัดการ state ในหน่วยความจำ
    get_state,
    set_baseline,
    should_alert,
    mark_alerted,
)
from app.features.alerts.percentage_change import (  # ตรรกะคำนวณ % และ hysteresis
    evaluate_percentage_alert,
)

# ===== พยายามใช้ price provider หลัก ถ้าไม่มีให้ fallback ไป crypto_price =====
try:
    from app.adapters.price_provider import get_price as provider_get_price  # ฟังก์ชันดึงราคาตัวเลขจาก provider
except Exception:  # หาก import ไม่ได้
    provider_get_price = None  # ตั้งให้เป็น None เพื่อไปใช้ fallback

try:
    # fallback: ใน utils.crypto_price ของคุณควรมีฟังก์ชันที่คืน "ตัวเลข" (หากไม่มี จะเกิด Exception)
    from app.utils.crypto_price import get_price as crypto_get_price  # ฟังก์ชัน fallback ดึงราคาตัวเลข
except Exception:  # หากไม่มีฟังก์ชันตัวเลขจริง ๆ
    crypto_get_price = None  # ตั้งให้ None และจะ raise Error ตอนเรียกใช้


def _get_numeric_price(symbol: str) -> float:
    """ดึงราคาปัจจุบันของสัญลักษณ์เป็น 'ตัวเลข float'
    ลำดับความพยายาม: price_provider → utils.crypto_price
    """
    if provider_get_price is not None:  # ถ้ามี provider หลัก
        price = provider_get_price(symbol)  # เรียกดึงราคาจาก provider
        if price is None:  # กันกรณี provider คืน None
            raise RuntimeError("price_provider.get_price() returned None")  # แจ้งเตือนชัดเจน
        return float(price)  # แปลงเป็น float เพื่อความชัดเจน
    if crypto_get_price is not None:  # ถ้าไม่มี provider ให้ลอง fallback
        price = crypto_get_price(symbol)  # ดึงราคาจาก utils.crypto_price
        if price is None:  # กัน None
            raise RuntimeError("crypto_price.get_price() returned None")  # แจ้งเตือน
        return float(price)  # แปลงเป็น float
    # ถ้าทั้งคู่ไม่มีให้ใช้งาน ให้โยน error เพื่อบอกให้ผู้ใช้เติมฟังก์ชัน
    raise RuntimeError("No numeric price source available. Please implement adapters.price_provider.get_price or utils.crypto_price.get_price.")


def _format_alert_text(symbol: str, current_price: float, pct_change: float) -> str:
    """สร้างข้อความแจ้งเตือนสำหรับส่ง LINE"""
    direction = "↑" if pct_change >= 0 else "↓"  # เลือกทิศทางลูกศรจากสัญญาณบวก/ลบ
    return f"[ALERT] {symbol} {direction}{abs(pct_change):.2f}% | Price: {current_price:,.2f} USD"  # ข้อความสั้นกระชับ


def _try_send_line_message(text: str) -> None:
    """พยายามส่งข้อความผ่าน LINE adapters (push หรือ broadcast)
    หมายเหตุ: ฟังก์ชันจริงในโปรเจกต์คุณอาจชื่อไม่ตรงกัน จึงลองหลายชื่อและจับข้อผิดพลาดไว้
    """
    try:
        # พยายามนำเข้าโมดูลจัดส่งของคุณ (ตั้งชื่อตามโปรเจกต์)
        from app.adapters.delivery_line import push_message, broadcast_message  # type: ignore  # พยายามดึงฟังก์ชันที่อาจมี
    except Exception:
        logger.warning("LINE delivery adapter not available; skip sending message.")  # แจ้งเตือนว่าไม่มีตัวส่ง LINE
        return  # ออกโดยไม่ส่ง

    # พยายามส่งแบบ broadcast ก่อน ถ้ามี (ไม่ต้องรู้ user_id)
    try:
        if 'broadcast_message' in locals():  # ถ้ามีฟังก์ชัน broadcast
            broadcast_message(text)  # ส่งข้อความแบบ broadcast
            return  # ส่งแล้วก็จบ
    except Exception as e:
        logger.warning("broadcast_message failed: %s", e)  # แจ้งเตือนถ้า broadcast ล้มเหลว

    # ถ้าไม่มี broadcast ให้ลอง push_message โดยต้องการ user_id (จำเป็นต้องปรับให้ตรงระบบจริงของคุณ)
    try:
        # TODO: ปรับที่มาของ user_id ให้เหมาะกับระบบของคุณ (เช่นอ่านจากฐานข้อมูลหรือไฟล์ config)
        USER_ID: Optional[str] = None  # ค่าเริ่มต้น None เพื่อหลีกเลี่ยงการส่งผิด
        if USER_ID:
            push_message(USER_ID, text)  # ถ้ามี user_id จะส่ง push
        else:
            logger.warning("No USER_ID available for push_message; skip sending message.")  # ไม่มี user_id จึงข้าม
    except Exception as e:
        logger.error("push_message failed: %s", e)  # แจ้ง error ถ้าส่ง push ไม่สำเร็จ


async def tick_once(dry_run: bool = False) -> None:
    """ทำงาน 1 รอบของ scheduler:
    1) ดึงราคาปัจจุบันของสัญลักษณ์ (ค่าเริ่มต้นจาก settings)
    2) ถ้ายังไม่มี baseline ให้ตั้ง baseline แล้วจบรอบ (ยังไม่แจ้ง)
    3) คำนวณ % การเปลี่ยนแปลงและ hysteresis
    4) ตรวจ cooldown (ใช้ should_alert จาก state_store)
    5) ถ้าพร้อมแจ้งและไม่ dry-run → ส่ง LINE และ mark_alerted → รีเซ็ต baseline เป็นราคาปัจจุบัน
    """
    if not alert_settings.enabled:  # ถ้าปิดฟีเจอร์ไว้
        logger.debug("Alert is disabled; skip tick.")  # บันทึกว่าไม่ทำงาน
        return  # ออกจากฟังก์ชัน

    symbol = alert_settings.symbol.upper()  # อ่านสัญลักษณ์จาก settings และแปลงเป็นตัวใหญ่
    threshold = float(alert_settings.threshold_pct)  # อ่านเกณฑ์ % ที่ต้องแจ้ง
    cooldown = int(alert_settings.cooldown_sec)  # อ่านค่า cooldown (วินาที)
    hysteresis = float(alert_settings.hysteresis_pct)  # อ่านค่า hysteresis (กันสัญญาณสั่น)

    # ดึงราคา ณ ปัจจุบัน
    current_price = _get_numeric_price(symbol)  # ดึงราคาตัวเลข (float)
    state = get_state(symbol)  # อ่าน state ปัจจุบันของ symbol
    baseline = state.get("baseline")  # อ่าน baseline จาก state
    last_state = state.get("last_state", "idle")  # อ่าน last_state (ค่าเริ่มเป็น idle ถ้าไม่พบ)

    # ถ้ายังไม่มี baseline ให้ตั้ง baseline แล้วออก (รอบแรกจะไม่แจ้ง)
    if baseline is None:  # ถ้า baseline ยังไม่ถูกตั้ง
        set_baseline(symbol, current_price)  # ตั้ง baseline เป็นราคาปัจจุบัน และตั้ง state = 'armed'
        logger.info("Baseline set for %s at %.6f; waiting for next tick.", symbol, current_price)  # บันทึกการตั้ง baseline
        return  # จบการทำงานรอบนี้

    # ประเมินสภาวะแจ้งเตือน (คำนวณ % และ hysteresis) ไม่รวม cooldown
    result = evaluate_percentage_alert(  # เรียกฟังก์ชันประเมินจากโมดูล alerts
        current_price=current_price,  # ราคาปัจจุบัน
        baseline_price=baseline,  # ราคาตั้งต้น
        threshold_pct=threshold,  # เกณฑ์ %
        hysteresis_pct=hysteresis,  # hysteresis
        last_state=last_state,  # สถานะเดิม (armed/idle)
    )
    pct = float(result["pct_change"])  # ดึงค่า % การเปลี่ยนแปลง
    crossed = bool(result["crossed"])  # ข้ามเกณฑ์หรือยัง (True/False)
    ready_by_hysteresis = bool(result["ready_to_alert"])  # พร้อมแจ้งตาม hysteresis ไหม
    new_state = str(result["new_state"])  # สถานะใหม่หลังประเมิน hysteresis

    # ตรวจ cooldown (รวมเงื่อนไขสุดท้ายว่าพร้อมแจ้งจริงหรือไม่)
    ready_by_cooldown = should_alert(symbol, pct_change=pct, threshold_pct=threshold, cooldown_sec=cooldown)  # ตรวจ cooldown
    ready_to_fire = ready_by_hysteresis and ready_by_cooldown  # ต้องผ่านทั้ง hysteresis และ cooldown

    # ล็อกสถานะรอบนี้เพื่อดีบัก
    logger.info(
        "TICK %s: price=%.6f baseline=%.6f pct=%+.3f%% crossed=%s hysteresis_ok=%s cooldown_ok=%s new_state=%s",
        symbol, current_price, baseline, pct, crossed, ready_by_hysteresis, ready_by_cooldown, new_state,
    )

    # อัปเดตสถานะใหม่ (เช่น จาก 'idle' → 'armed' เมื่อถอยกลับเข้า hysteresis)
    state["last_state"] = new_state  # เขียนสถานะใหม่กลับเข้า state

    # ถ้าพร้อมแจ้งแล้ว
    if ready_to_fire:  # เงื่อนไขพร้อมยิงแจ้งเตือน
        text = _format_alert_text(symbol, current_price, pct)  # สร้างข้อความแจ้งเตือน
        if dry_run:  # ถ้าเป็นโหมดทดลอง
            logger.info("[DRY-RUN] Would send LINE: %s", text)  # พิมพ์เฉย ๆ ไม่ส่งจริง
        else:  # โหมดจริง
            _try_send_line_message(text)  # พยายามส่งข้อความไป LINE

        # ทำเครื่องหมายว่าเพิ่งแจ้ง และรีเซ็ต baseline เป็นราคาปัจจุบันสำหรับรอบถัดไป
        mark_alerted(symbol)  # บันทึกเวลา alert ล่าสุด + สลับ state เป็น 'idle'
        set_baseline(symbol, current_price)  # รีเซ็ต baseline ใหม่ (และ armed ใหม่) เพื่อจับรอบถัดไป
        logger.info("Alert fired; baseline reset for %s at %.6f", symbol, current_price)  # บันทึกการรีเซ็ต baseline


async def run_scheduler() -> None:
    """วนลูปเรียก tick_once() ทุก alert_settings.poll_sec วินาที"""
    poll = int(alert_settings.poll_sec)  # อ่านค่า poll interval จาก settings
    logger.info("Scheduler started: poll every %ds (symbol=%s, threshold=%.2f%%, cooldown=%ds, hysteresis=%.2f%%)",
                poll, alert_settings.symbol.upper(), alert_settings.threshold_pct, alert_settings.cooldown_sec, alert_settings.hysteresis_pct)  # ล็อกค่าตั้งต้น
    try:
        while True:  # ลูปไม่รู้จบ
            await tick_once(dry_run=False)  # เรียกทำงาน 1 รอบแบบจริง
            await asyncio.sleep(poll)  # พักตามช่วงที่กำหนด
    except asyncio.CancelledError:  # ถ้าถูกยกเลิกลูปจากภายนอก
        logger.info("Scheduler cancelled; shutting down.")  # แจ้งการปิดตัว
    except Exception as e:  # กันข้อผิดพลาดไม่ให้ล้มทั้งลูป
        logger.exception("Scheduler encountered an error: %s", e)  # พิมพ์ stacktrace เพื่อดีบัก
        await asyncio.sleep(poll)  # หน่วงก่อนลองรอบถัดไป


# ===== 🧪 คำสั่งทดสอบ =====
# 1) ทดสอบทำงาน 1 รอบแบบ dry-run (ไม่ส่ง LINE จริง):
# python3 -c "from app.scheduler.runner import tick_once; import asyncio; asyncio.run(tick_once(dry_run=True))"
#
# 2) รัน scheduler วนลูป (ระวัง: จะไม่จบเอง กด Ctrl+C เพื่อหยุด):
# python3 -c "from app.scheduler.runner import run_scheduler; import asyncio; asyncio.run(run_scheduler())"
#
# ✅ Acceptance:
# - คำสั่ง (1) รันแล้วไม่ error และเห็น log แสดงการประเมิน pct/cooldown/hysteresis
# - เมื่อราคาเคลื่อน ≥ ±threshold และ state = 'armed' → โหมดจริงจะส่ง LINE 1 ครั้ง, mark_alerted(), และตั้ง baseline ใหม่เป็นราคาปัจจุบัน
# - ภายใน COOLDOWN จะไม่ยิงซ้ำ (ready_by_cooldown=False)
