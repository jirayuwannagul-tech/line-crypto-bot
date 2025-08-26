#!/usr/bin/env python3
"""
Mock price alert (single-file)
- จำลองราคาวิ่งไปหา entry แล้วแจ้งเตือนครั้งเดียว
- ถ้ามี LINE token + ระบุ --to จะ Push LINE จริง
- ถ้าไม่มี จะพิมพ์แจ้งในคอนโซลแทน

ใช้งาน:
  python scripts/mock_price_alert.py --symbol BTCUSDT --entry 60000 --tol 50 --to <USER_ID>
หรือทดสอบแบบพิมพ์อย่างเดียว:
  python scripts/mock_price_alert.py --symbol BTCUSDT --entry 60000 --tol 50
"""

from __future__ import annotations
import os, time, argparse, math
from typing import Optional, List

# ────────────── LINE Push (optional) ──────────────
def try_push_line(user_id: Optional[str], text: str) -> bool:
    """
    ถ้ามี token + user_id จะ push จริง; ไม่งั้นคืน False
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or not user_id:
        return False
    try:
        from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
        cfg = Configuration(access_token=token)
        with ApiClient(cfg) as c:
            MessagingApi(c).push_message(
                PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
            )
        print("[PUSH] sent to LINE.")
        return True
    except Exception as e:
        print(f"[PUSH] failed: {e}")
        return False

# ────────────── Mock price stream ──────────────
def mock_prices_toward(target: float, start: Optional[float] = None, steps: int = 10) -> List[float]:
    """
    สร้างลิสต์ราคาไล่เข้าใกล้ target แบบง่าย ๆ
    """
    if start is None:
        # ถ้าไม่ได้ระบุ start ให้เริ่มห่างสัก 1.5% ลง/ขึ้นแบบสุ่มเล็กน้อย
        start = target * (0.985 if target > 0 else 1.0)
    step = (target - start) / max(steps, 1)
    return [start + i * step for i in range(steps)] + [target, target + step]

def fmt(x: Optional[float]) -> str:
    if x is None: return "-"
    x = float(x)
    if abs(x) >= 1000: return f"{x:,.2f}"
    if abs(x) >= 1:    return f"{x:.4f}"
    return f"{x:.6f}"

def main():
    ap = argparse.ArgumentParser(description="Mock price alert tester")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--entry", type=float, required=True, help="ราคาเข้าที่ต้องการ")
    ap.add_argument("--tol", type=float, default=0.0, help="ค่าความคลาดเคลื่อน ±tol (เช่น 50)")
    ap.add_argument("--start", type=float, default=None, help="ราคาเริ่มจำลอง (ไม่ใส่จะ auto)")
    ap.add_argument("--steps", type=int, default=10, help="จำนวนสเต็ปก่อนแตะ")
    ap.add_argument("--interval", type=float, default=1.0, help="หน่วงเวลาต่อสเต็ป (วินาที)")
    ap.add_argument("--to", default=None, help="LINE userId สำหรับ push (ถ้าไม่ใส่จะพิมพ์ในคอนโซล)")
    args = ap.parse_args()

    symbol = args.symbol.upper().replace(":", "").replace("/", "")
    entry  = float(args.entry)
    tol    = float(args.tol)
    prices = mock_prices_toward(entry, start=args.start, steps=args.steps)

    print(f"👟 เริ่มจำลอง {symbol} ไปที่ {fmt(entry)} tol=±{fmt(tol)} (steps={len(prices)}, interval={args.interval}s)")
    hit_once = False

    for px in prices:
        print(f"[TICK] {symbol} = {fmt(px)}")
        # เงื่อนไข hit: ถ้ามี tol → อยู่ในช่วง |px-entry|<=tol, ถ้าไม่มีก็เท่ากันเป๊ะ
        hit = (abs(px - entry) <= tol) if tol > 0 else (px == entry)
        if hit and not hit_once:
            msg = (
                f"🔔 ราคาแตะ {symbol}\n"
                f"• Price: {fmt(px)}\n"
                f"• Entry: {fmt(entry)}\n"
                + (f"• Tol: ±{fmt(tol)}\n" if tol > 0 else "")
            )
            pushed = try_push_line(args.to, msg)
            if not pushed:
                print(msg)
            hit_once = True
        time.sleep(max(args.interval, 0.05))

    if not hit_once:
        print("ℹ️ ยังไม่แตะ entry (ลองเพิ่ม steps, tol หรือปรับ start)")

if __name__ == "__main__":
    main()
