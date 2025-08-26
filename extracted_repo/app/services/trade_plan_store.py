"""
trade_plan_store.py
===================

Service สำหรับบันทึกและโหลด "แผนเทรด/สัญญาณ" ที่ระบบสร้างขึ้น
- เก็บลง CSV (trade_plans.csv) ในโฟลเดอร์ app/data/
- โครงสร้างแบ่งเป็นชั้น (Layer) เพื่อให้ขยายง่าย
"""

import os
import csv
import datetime
from typing import List, Dict, Any, Optional

# =============================================================================
# CONFIG LAYER
# =============================================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
FILE_PATH = os.path.join(DATA_DIR, "trade_plans.csv")

# สร้างโฟลเดอร์ data ถ้าไม่มี
os.makedirs(DATA_DIR, exist_ok=True)

# =============================================================================
# SCHEMA LAYER
# =============================================================================
FIELDS: List[str] = [
    "timestamp", "symbol", "timeframe", "direction",
    "entry", "tp1", "tp2", "tp3", "sl",
    "prob_up", "prob_down", "prob_side",
    "ema50", "ema200", "high", "low",
    "reason",
    "tp1_hit", "tp2_hit", "tp3_hit", "sl_hit",
    "closed_at"
]

# =============================================================================
# STORAGE LAYER (CSV)
# =============================================================================
def _init_file() -> None:
    """สร้างไฟล์ CSV พร้อม header ถ้ายังไม่มี"""
    if not os.path.exists(FILE_PATH):
        with open(FILE_PATH, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()

def _read_all() -> List[Dict[str, Any]]:
    """อ่าน trade plans ทั้งหมดจาก CSV"""
    _init_file()
    with open(FILE_PATH, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def _write_all(rows: List[Dict[str, Any]]) -> None:
    """เขียน trade plans ทั้งหมดทับไฟล์"""
    with open(FILE_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

# =============================================================================
# SERVICE LAYER
# =============================================================================
def save_trade_plan(plan: Dict[str, Any]) -> None:
    """
    บันทึกแผนเทรดใหม่ลง CSV
    จะเติมค่า timestamp อัตโนมัติ
    """
    _init_file()
    rows = _read_all()

    # timestamp ตอนนี้
    ts = datetime.datetime.utcnow().isoformat()
    plan["timestamp"] = ts

    # ให้แน่ใจว่ามี field ครบ
    for field in FIELDS:
        if field not in plan:
            plan[field] = ""

    rows.append(plan)
    _write_all(rows)

def list_trade_plans(open_only: bool = False) -> List[Dict[str, Any]]:
    """
    ดึง trade plans ทั้งหมด
    - ถ้า open_only=True จะคืนเฉพาะที่ยังไม่ปิด (closed_at="")
    """
    rows = _read_all()
    if open_only:
        rows = [r for r in rows if not r.get("closed_at")]
    return rows

def mark_closed(timestamp: str, reason: str) -> bool:
    """
    ปิดแผนเทรดตาม timestamp และใส่ closed_at
    return True ถ้าปิดสำเร็จ
    """
    rows = _read_all()
    updated = False
    for r in rows:
        if r.get("timestamp") == timestamp:
            r["closed_at"] = f"{datetime.datetime.utcnow().isoformat()} ({reason})"
            updated = True
            break
    if updated:
        _write_all(rows)
    return updated

def mark_target_hit(timestamp: str, target: str) -> bool:
    """
    อัปเดตว่า TP1/TP2/TP3/SL ถูก hit แล้ว
    target ต้องเป็น 'tp1' | 'tp2' | 'tp3' | 'sl'
    """
    if target not in ["tp1", "tp2", "tp3", "sl"]:
        raise ValueError("target ต้องเป็น tp1|tp2|tp3|sl")

    rows = _read_all()
    updated = False
    for r in rows:
        if r.get("timestamp") == timestamp:
            r[f"{target}_hit"] = "1"
            updated = True
            break
    if updated:
        _write_all(rows)
    return updated

# =============================================================================
# DEBUG / TEST
# =============================================================================
if __name__ == "__main__":
    # ตัวอย่างการใช้งาน
    sample_plan = {
        "symbol": "BTCUSDT",
        "timeframe": "1D",
        "direction": "SHORT",
        "entry": "111920",
        "tp1": "108201.56",
        "tp2": "105970.60",
        "tp3": "103739.64",
        "sl": "114894.44",
        "prob_up": "17",
        "prob_down": "70",
        "prob_side": "13",
        "ema50": "114755.97",
        "ema200": "103688.96",
        "high": "124474",
        "low": "111920",
        "reason": "Dow SIDE; Elliott Unknown; Weekly DOWN bias"
    }
    save_trade_plan(sample_plan)
    print("✅ saved trade plan")

    all_plans = list_trade_plans()
    print("📋 all plans:", all_plans)
