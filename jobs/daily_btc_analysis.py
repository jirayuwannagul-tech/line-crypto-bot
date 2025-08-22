# jobs/daily_btc_analysis.py
"""
Daily BTC Analysis Job
ดึง BTCUSDT 1D (จาก provider) → อัปเดต app/data/historical.xlsx → ส่งเข้า engine วิเคราะห์
ถ้ามีสัญญาณเข้าออก → ส่ง LINE แจ้งเตือน

วิธีรัน:
    python -m jobs.daily_btc_analysis
หรือเพิ่มใน Procfile:
    daily-btc: python -m jobs.daily_btc_analysis
"""

from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
import traceback

import pandas as pd

# === โปรเจกต์โมดูล ===
from app.analysis.timeframes import get_data
from app.services.wave_service import analyze_wave, build_brief_message
from app.analysis.entry_exit import suggest_trade, format_trade_text
from app.adapters import delivery_line as line

HIST_PATH = "app/data/historical.xlsx"
SYMBOL = "BTCUSDT"
TF = "1D"
PROFILE = os.getenv("STRATEGY_PROFILE", "baseline")

# LINE targets (ถ้าไม่ได้ตั้ง จะใช้ broadcast)
LINE_TO = os.getenv("LINE_DEFAULT_TO", "").strip()


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def save_df_to_excel(df: pd.DataFrame, path: str, sheet: str):
    """
    บันทึกแทนทั้งชีท (ปลอดภัยสุด ลดปัญหา schema mismatch)
    - index เป็น datetime/str ได้ทั้งคู่
    - คาดว่า df เป็น OHLCV + อินดิเคเตอร์ได้ (จะเก็บเท่าที่มี)
    """
    mode = "a" if os.path.exists(path) else "w"
    if mode == "a":
        # ลบชีทเดิมก่อนแล้วเขียนใหม่ เพื่อกันคอลัมน์เพี้ยน
        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name=sheet, index=True)
    else:
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            df.to_excel(writer, sheet_name=sheet, index=True)


def send_line(text: str):
    """
    ส่ง LINE แบบยืดหยุ่น:
    - ถ้ามี LINE_DEFAULT_TO → push ไปยัง id นั้น
    - ไม่มีก็ broadcast
    """
    try:
        if LINE_TO:
            line.push_message(LINE_TO, text)   # โปรเจกต์นี้ส่วนใหญ่รองรับ (to, text)
        else:
            line.broadcast(text)
    except TypeError:
        # เผื่อบางเวอร์ชันของ delivery_line ใช้ signature ที่ต่างออกไป
        try:
            line.push_message(text)
        except Exception:
            line.broadcast(text)


def main():
    print(f"[{_now_utc()}] Start daily BTC analysis job")

    # 1) โหลดราคาสด (ไม่ส่ง xlsx_path) → 1D ล่าสุดเต็มช่วง
    print("• Fetching fresh OHLCV from provider (1D)…")
    df_1d = get_data(SYMBOL, TF)   # ในโปรเจกต์คุณรองรับ “โหลดราคาสดจาก provider (ไม่ส่ง xlsx_path)”
    if df_1d is None or len(df_1d) == 0:
        raise RuntimeError("get_data() returned empty df")

    # 2) อัปเดต historical.xlsx (ชีท: BTCUSDT_1D) ให้เป็นข้อมูลล่าสุดเสมอ
    sheet_name = f"{SYMBOL}_{TF}"
    print(f"• Writing latest data to {HIST_PATH} (sheet: {sheet_name}) … rows={len(df_1d)}")
    save_df_to_excel(df_1d, HIST_PATH, sheet_name)

    # 3) วิเคราะห์ด้วย engine / services ที่มีอยู่
    #    - ใช้ xlsx_path เพื่อให้ pipeline อื่น ๆ อ้างอิงไฟล์เดียวกัน
    print("• Analyzing wave/summary from historical.xlsx …")
    payload = analyze_wave(SYMBOL, TF, xlsx_path=HIST_PATH)
    brief = build_brief_message(payload)

    # 4) สร้างสัญญาณเข้า/ออกตามโปรไฟล์ (ใช้ df จาก payload ถ้ามี ไม่งั้นให้ suggest_trade โหลดเอง)
    print("• Building trade suggestion …")
    df_for_trade = payload.get("debug", {}).get("df")
    suggestion = suggest_trade(
        df_for_trade,
        symbol=SYMBOL,
        tf=TF,
        cfg={"profile": PROFILE, "xlsx_path": HIST_PATH},
    )
    trade_text = format_trade_text(suggestion)

    # 5) เกณฑ์ “มีสัญญาณ” → ส่ง LINE
    has_entry = False
    try:
        # รองรับทั้ง dict และ object-like
        entry = (suggestion or {}).get("entry") if isinstance(suggestion, dict) else getattr(suggestion, "entry", None)
        has_entry = bool(entry)
    except Exception:
        has_entry = False

    # สรุปข้อความเดียวสำหรับแปะ LINE
    header = f"🗓 {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Bangkok)\n"
    body = (
        f"📈 Daily BTC Analysis (from provider → saved to Excel)\n"
        f"{brief}\n\n"
        f"{trade_text}"
    )
    msg = header + body

    # ส่งแจ้งเตือนเมื่อ “มีสัญญาณใหม่” เท่านั้น
    if has_entry:
        print("• Signal detected → sending LINE …")
        send_line(msg)
    else:
        print("• No tradable signal → skip LINE. (You still can check logs)")

    print(f"[{_now_utc()}] Job done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = f"❌ Daily BTC job failed: {e}\n{traceback.format_exc()}"
        print(err, file=sys.stderr)
        # แจ้งเตือนความผิดพลาดผ่าน LINE (ไม่บังคับ)
        try:
            send_line(err[:1800])  # กันข้อความยาวเกิน
        except Exception:
            pass
        sys.exit(1)
