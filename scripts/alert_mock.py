#!/usr/bin/env python3
# Mock แจ้งเตือน TP/SL สำหรับแผน A) Short – Breakout
# ใช้: python scripts/alert_mock.py --price 110280.14

import argparse

# ====== กำหนดระดับตามแผน A ======
ENTRY = 111_920.00
SL    = 115_277.60
TP1   = 108_562.40
TP2   = 106_324.00
TP3   = 104_085.60

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--price", type=float, required=True, help="ราคาปัจจุบัน (BTCUSDT)")
    args = ap.parse_args()
    p = args.price

    hits = []
    if p <= TP1: hits.append("TP1")
    if p <= TP2: hits.append("TP2")
    if p <= TP3: hits.append("TP3")
    if p >= SL:  hits.append("SL")

    print(f"แผนที่ใช้งาน: Short – Breakout (A) | ENTRY {ENTRY:,.2f} | SL {SL:,.2f} | TP {TP1:,.2f}/{TP2:,.2f}/{TP3:,.2f}")
    if hits:
        print(f"LINE ALERT (mock): {' / '.join(hits)} | ราคา {p:,.2f}")
    else:
        side = "ใต้ ENTRY" if p < ENTRY else "เหนือ ENTRY"
        print(f"ยังไม่ถึง TP/SL | ราคา {p:,.2f} ({side})")

if __name__ == "__main__":
    main()
