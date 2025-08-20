"""
app/features/alerts/percentage_change.py
----------------------------------------
เลเยอร์: features/alerts
หน้าที่: ฟังก์ชันคำนวณ % การเปลี่ยนแปลงราคา และตรรกะ hysteresis สำหรับระบบแจ้งเตือน
ใช้งานร่วมกับ state_store (baseline/last_state/last_alert_ts) และ scheduler ภายหลัง
"""

from typing import Dict  # นำเข้า Dict เพื่อใช้ระบุชนิดข้อมูลของผลลัพธ์อย่างชัดเจน


def compute_pct_change(current_price: float, baseline_price: float) -> float:
    """คำนวณเปอร์เซ็นต์การเปลี่ยนแปลงจาก baseline
    สูตร: ((current - baseline) / baseline) * 100
    หมายเหตุ: baseline ต้องเป็นค่าบวกและไม่เป็น 0
    """
    if baseline_price is None or baseline_price == 0:  # กันกรณี baseline ว่างหรือศูนย์
        raise ValueError("baseline_price must be a non-zero number")  # แจ้งข้อผิดพลาดชัดเจน
    return ((current_price - baseline_price) / baseline_price) * 100.0  # คืนค่า % การเปลี่ยนแปลง


def crossed_threshold(pct_change: float, threshold_pct: float) -> bool:
    """ตรวจว่าแตะ/ข้ามเกณฑ์แจ้งเตือนหรือยัง (เช่น 5%)
    ใช้ค่า absoluted value เพราะสนใจทั้งขึ้นและลง
    """
    return abs(pct_change) >= threshold_pct  # จริงเมื่อเกินหรือเท่ากับ threshold


def should_rearm_after_alert(pct_change: float, threshold_pct: float, hysteresis_pct: float) -> bool:
    """หลังจากเพิ่งแจ้งเตือนแล้ว (state=idle) ต้อง “ถอยกลับ” เข้ามาในโซนปลอดภัยก่อนจึงจะ re-arm
    นิยามโซนปลอดภัย: |pct_change| <= (threshold_pct - hysteresis_pct)
    ตัวอย่าง: threshold=5, hysteresis=1 ⇒ ปลอดภัยเมื่อ |pct| <= 4
    """
    safe_band = max(threshold_pct - hysteresis_pct, 0.0)  # กันค่าติดลบกรณีตั้ง hysteresis มากเกิน
    return abs(pct_change) <= safe_band  # อยู่ในโซนปลอดภัยจึงพร้อม re-arm


def evaluate_percentage_alert(
    current_price: float,
    baseline_price: float,
    threshold_pct: float,
    hysteresis_pct: float,
    last_state: str,
) -> Dict[str, object]:
    """ประเมินสถานะการแจ้งเตือนแบบเปอร์เซ็นต์ + hysteresis (ไม่รวม cooldown)
    พฤติกรรม:
      - ถ้าอยู่สถานะ 'armed' และ |pct| >= threshold ⇒ ready_to_alert = True
      - ถ้าอยู่สถานะ 'idle' จะ re-arm เมื่อ |pct| <= (threshold - hysteresis)
    คืนค่า:
      {
        'pct_change': float,        # % เปลี่ยนแปลงปัจจุบัน
        'crossed': bool,            # ข้ามเกณฑ์แล้วหรือยัง
        'ready_to_alert': bool,     # พร้อมยิงแจ้งเตือน (ยังไม่เช็ค cooldown)
        'new_state': 'armed'|'idle' # สถานะใหม่ (หลังประเมิน hysteresis)
      }
    """
    pct = compute_pct_change(current_price, baseline_price)  # คำนวณ % เปลี่ยนจาก baseline
    crossed = crossed_threshold(pct, threshold_pct)  # ตรวจว่าข้าม threshold หรือยัง

    # เริ่มจากสถานะเดิม
    new_state = last_state  # ตั้งค่าเริ่มต้นเป็นสถานะเดิม
    ready_to_alert = False  # เริ่มต้นยังไม่พร้อมแจ้งเตือน

    if last_state == "armed":  # ถ้ายัง armed อยู่
        if crossed:  # และข้ามเกณฑ์แล้ว
            ready_to_alert = True  # พร้อมแจ้งเตือน (ส่วน cooldown ไปเช็คใน state_store/scheduler)
            new_state = "idle"  # ยิงแล้วจะสลับเป็น idle (รอให้ถอยเข้า hysteresis ก่อนค่อย armed ใหม่)
    else:  # กรณี last_state == "idle"
        if should_rearm_after_alert(pct, threshold_pct, hysteresis_pct):  # ถอยเข้าโซนปลอดภัยแล้วหรือยัง
            new_state = "armed"  # ถ้าถอยแล้ว ให้ armed เพื่อรอรอบแจ้งเตือนถัดไป

    return {
        "pct_change": pct,  # คืนค่า % การเปลี่ยนแปลง
        "crossed": crossed,  # คืนค่าว่าข้ามเกณฑ์หรือยัง
        "ready_to_alert": ready_to_alert,  # คืนค่าว่าพร้อมแจ้งหรือไม่ (ยังไม่รวม cooldown)
        "new_state": new_state,  # คืนค่าสถานะใหม่
    }


# ===== 🧪 คำสั่งทดสอบแบบง่าย (manual) =====
# python3 -c "from app.features.alerts.percentage_change import evaluate_percentage_alert; print(evaluate_percentage_alert(63000, 60000, 5, 1, 'armed'))"
# อธิบายคาดหวัง:
# - baseline=60000 → current=63000 ⇒ pct_change = +5.0%
# - last_state='armed' และข้ามเกณฑ์ 5% ⇒ ready_to_alert=True, new_state='idle'
#
# ✅ Acceptance:
# - เมื่อ current ขยับ ≥ ±threshold จาก baseline และ last_state='armed' ⇒ ready_to_alert=True, new_state='idle'
# - เมื่ออยู่ 'idle' แล้วราคา “ถอยกลับ” จน |pct| <= threshold-hysteresis ⇒ new_state กลับเป็น 'armed'
# - ฟังก์ชันไม่โยน exception เมื่อรับค่าปกติ (baseline > 0) และผลสอดคล้องกับสูตร
