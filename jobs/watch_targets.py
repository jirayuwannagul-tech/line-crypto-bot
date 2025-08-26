"""
watch_targets.py
================

Job สำหรับเฝ้าราคา → ตรวจสอบว่าแตะ TP/SL ของแผนเทรดที่ยังเปิดอยู่หรือไม่
- ดึง trade plans จาก trade_plan_store
- ดึงราคาล่าสุดจาก price_provider_binance
- ถ้าแตะเป้า → อัปเดตสถานะ (mark_target_hit/mark_closed)
- ส่งแจ้งเตือนผ่าน notifier_line
"""

import time
import traceback
from typing import Dict, Any

# =============================================================================
# CONFIG LAYER
# =============================================================================
CHECK_INTERVAL = 15  # วินาที, ความถี่ในการเช็คราคา

# =============================================================================
# DATA LAYER
# =============================================================================
from app.services import trade_plan_store
from app.services import notifier_line
from app.services import price_provider_binance


def get_current_price(symbol: str) -> float:
    """ดึงราคาล่าสุดของ symbol"""
    return price_provider_binance.get_price(symbol)


# =============================================================================
# SERVICE LAYER
# =============================================================================
def check_plan(plan: Dict[str, Any]) -> None:
    """
    ตรวจสอบแผนเทรดเดี่ยวว่ามีการแตะ TP/SL หรือยัง
    """
    symbol = plan["symbol"]
    ts = plan["timestamp"]

    try:
        price = get_current_price(symbol)
    except Exception as e:
        print(f"⚠️ error fetching price {symbol}: {e}")
        return

    # ดึงค่าเป้าหมาย
    entry = float(plan.get("entry") or 0)
    tp1 = float(plan.get("tp1") or 0)
    tp2 = float(plan.get("tp2") or 0)
    tp3 = float(plan.get("tp3") or 0)
    sl = float(plan.get("sl") or 0)
    direction = plan.get("direction", "").upper()

    hit_messages = []

    if direction == "SHORT":
        if not plan.get("tp1_hit") and price <= tp1:
            trade_plan_store.mark_target_hit(ts, "tp1")
            hit_messages.append(f"✅ TP1 {tp1} hit @ {price}")
        if not plan.get("tp2_hit") and price <= tp2:
            trade_plan_store.mark_target_hit(ts, "tp2")
            hit_messages.append(f"✅ TP2 {tp2} hit @ {price}")
        if not plan.get("tp3_hit") and price <= tp3:
            trade_plan_store.mark_target_hit(ts, "tp3")
            trade_plan_store.mark_closed(ts, "TP3 reached")
            hit_messages.append(f"🏆 TP3 {tp3} hit @ {price} → Plan Closed")
        if not plan.get("sl_hit") and price >= sl:
            trade_plan_store.mark_target_hit(ts, "sl")
            trade_plan_store.mark_closed(ts, "Stop Loss")
            hit_messages.append(f"❌ SL {sl} hit @ {price} → Plan Closed")

    elif direction == "LONG":
        if not plan.get("tp1_hit") and price >= tp1:
            trade_plan_store.mark_target_hit(ts, "tp1")
            hit_messages.append(f"✅ TP1 {tp1} hit @ {price}")
        if not plan.get("tp2_hit") and price >= tp2:
            trade_plan_store.mark_target_hit(ts, "tp2")
            hit_messages.append(f"✅ TP2 {tp2} hit @ {price}")
        if not plan.get("tp3_hit") and price >= tp3:
            trade_plan_store.mark_target_hit(ts, "tp3")
            trade_plan_store.mark_closed(ts, "TP3 reached")
            hit_messages.append(f"🏆 TP3 {tp3} hit @ {price} → Plan Closed")
        if not plan.get("sl_hit") and price <= sl:
            trade_plan_store.mark_target_hit(ts, "sl")
            trade_plan_store.mark_closed(ts, "Stop Loss")
            hit_messages.append(f"❌ SL {sl} hit @ {price} → Plan Closed")

    # แจ้งเตือนทุกเป้าที่โดน
    for msg in hit_messages:
        notifier_line.send_message(f"[{symbol}] {msg}")


def check_all_plans() -> None:
    """ตรวจสอบแผนทั้งหมดที่ยังเปิดอยู่"""
    plans = trade_plan_store.list_trade_plans(open_only=True)
    if not plans:
        print("ℹ️ no open trade plans")
        return

    for plan in plans:
        try:
            check_plan(plan)
        except Exception:
            traceback.print_exc()


# =============================================================================
# RUNNER LAYER
# =============================================================================
def run_loop() -> None:
    """วน loop ตรวจสอบทุกๆ CHECK_INTERVAL วินาที"""
    print("🚀 starting watch_targets loop...")
    while True:
        check_all_plans()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_loop()
