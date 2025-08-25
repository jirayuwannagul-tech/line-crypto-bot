# app/services/message_templates.py
from __future__ import annotations
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None  # fallback: ใช้ UTC อย่างเดียว

def build_price_message(symbol: str, price: float, quote: str = "USDT") -> str:
    """
    สร้างข้อความสั้นสำหรับแจ้งเตือนราคา
    แสดงเวลา UTC และเวลาไทย (Asia/Bangkok)
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if ZoneInfo:
        now_bkk = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S Asia/Bangkok")
        local_line = f"\nเวลา: {now_bkk}"
    else:
        local_line = ""

    msg = (
        f"📈 {symbol.upper()} — ราคาอัปเดตทุกชั่วโมง\n"
        f"ราคา: {price:,.2f} {quote.upper()}\n"
        f"เวลา: {now_utc}{local_line}"
    )
    return msg
