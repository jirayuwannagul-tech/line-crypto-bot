# jobs/daily_btc_analysis.py
"""
Daily BTC Analysis Job
ดึง BTCUSDT 1D → อัปเดต app/data/historical.xlsx → ส่งเข้า engine วิเคราะห์
ถ้ามีสัญญาณเข้า/ออก → ส่ง LINE แจ้งเตือน

วิธีรัน:
    python -m jobs.daily_btc_analysis
หรือเพิ่มใน Procfile:
    daily-btc: python -m jobs.daily_btc_analysis
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone

import pandas as pd
from pandas.api.types import is_datetime64tz_dtype

# === โปรเจกต์โมดูล ===
from app.analysis.timeframes import get_data
from app.services.wave_service import analyze_wave, build_brief_message
from app.analysis.entry_exit import suggest_trade, format_trade_text
from app.adapters import delivery_line as line

# ---------------- Config ----------------
HIST_PATH = "app/data/historical.xlsx"
SYMBOL = "BTCUSDT"
TF = "1D"
PROFILE = os.getenv("STRATEGY_PROFILE", "baseline")  # baseline | chinchot | cholak
LINE_TO = os.getenv("LINE_DEFAULT_TO", "").strip()   # ถ้าเว้นว่างจะ broadcast

# -------------- Helpers -----------------
def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def _excel_sanitize_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    """
    ทำให้ทุก datetime เป็น tz-naive (Excel ไม่รองรับ tz-aware)
    - แปลง index ถ้าเป็น DatetimeIndex ที่มี tz → แปลงเป็น UTC แล้วตัด tz ออก
    - แปลงคอลัมน์ที่เป็น datetime64[ns, tz] → UTC → tz-naive
    """
    out = df.copy()
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_convert("UTC").tz_localize(None)
    for col in out.columns:
        s = out[col]
        if is_datetime64tz_dtype(s):
            out[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return out

def save_df_to_excel(df: pd.DataFrame, path: str, sheet: str) -> None:
    """
    เขียนทั้งชีท (replace) เพื่อกัน schema เพี้ยน + ทำ tz‑naive เสมอ
    """
    # สร้างโฟลเดอร์ถ้ายังไม่มี
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # บังคับให้ timestamp เป็นคอลัมน์ (กรณีเป็น index อยู่ก่อน)
    df_to_write = df.copy()
    if "timestamp" not in df_to_write.columns:
        # ถ้า index เป็นเวลาจะย้ายมาไว้ในคอลัมน์ timestamp
        if isinstance(df_to_write.index, pd.DatetimeIndex):
            df_to_write = df_to_write.reset_index().rename(columns={"index": "timestamp"})

    # ล้าง tz ในทุก datetime
    df_to_write = _excel_sanitize_datetimes(df_to_write)

    mode = "a" if os.path.exists(path) else "w"
    if mode == "a":
        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df_to_write.to_excel(writer, sheet_name=sheet, index=False)
    else:
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            df_to_write.to_excel(writer, sheet_name=sheet, index=False)

def send_line(text: str) -> None:
    """
    ส่ง LINE แบบยืดหยุ่น:
    - ถ้ามี LINE_DEFAULT_TO → push ไปยัง id นั้น
    - ไม่มีก็ broadcast
    """
    try:
        if LINE_TO:
            line.push_message(LINE_TO, text)
        else:
            line.broadcast(text)
    except TypeError:
        # เผื่อ signature แตกต่างในบางเวอร์ชัน
        try:
            line.push_message(text)
        except Exception:
            line.broadcast(text)

# --------------- Main -------------------
def main() -> None:
    print(f"[{_now_utc_str()}] Start daily BTC analysis job")

    # 1) โหลดราคาสด (ไม่ส่ง xlsx_path) → 1D ล่าสุดเต็มช่วง
    print("• Fetching fresh OHLCV from provider (1D)…")
    df_1d = get_data(SYMBOL, TF)  # ตอนนี้ get_data รองรับ fallback ccxt อยู่ในตัวแล้ว

    # แสดงผลลัพธ์สั้น ๆ
    n = len(df_1d) if df_1d is not None else 0
    t0 = str(df_1d["timestamp"].iloc[0]) if n else "-"
    t1 = str(df_1d["timestamp"].iloc[-1]) if n else "-"
    print(f"• Loaded OHLCV rows={n} range={t0} → {t1}")
    if n == 0:
        raise RuntimeError("get_data() returned empty df")

    # 2) อัปเดต historical.xlsx (ชีท: BTCUSDT_1D) ให้เป็นข้อมูลล่าสุดเสมอ
    sheet_name = f"{SYMBOL}_{TF}"
    print(f"• Writing latest data to {HIST_PATH} (sheet: {sheet_name}) … rows={n}")
    save_df_to_excel(df_1d, HIST_PATH, sheet_name)

    # 3) วิเคราะห์จากไฟล์เดียวกัน (ให้ pipeline อื่นอ้างอิงสอดคล้อง)
    print("• Analyzing wave/summary from historical.xlsx …")
    payload = analyze_wave(SYMBOL, TF, xlsx_path=HIST_PATH)
    brief = build_brief_message(payload)

    # 4) สร้างสัญญาณเข้า/ออกตามโปรไฟล์ (ใช้ df จาก payload ถ้ามี)
    print("• Building trade suggestion …")
    try:
        df_for_trade = payload.get("debug", {}).get("df")
    except Exception:
        df_for_trade = None

    suggestion = suggest_trade(
        df_for_trade,
        symbol=SYMBOL,
        tf=TF,
        cfg={"profile": PROFILE, "xlsx_path": HIST_PATH},
    )
    trade_text = format_trade_text(suggestion)

    # 5) ถ้ามีสัญญาณ → ส่ง LINE
    try:
        entry = (suggestion or {}).get("entry") if isinstance(suggestion, dict) \
            else getattr(suggestion, "entry", None)
        has_entry = bool(entry)
    except Exception:
        has_entry = False

    header = f"🗓 {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Bangkok)\n"
    body = (
        f"📈 Daily BTC Analysis (from provider → saved to Excel)\n"
        f"{brief}\n\n"
        f"{trade_text}"
    )
    msg = header + body

    if has_entry:
        print("• Signal detected → sending LINE …")
        send_line(msg)
    else:
        print("• No tradable signal → skip LINE. (You still can check logs)")

    print(f"[{_now_utc_str()}] Job done.")

# ------------- Entrypoint --------------
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = f"❌ Daily BTC job failed: {e}\n{traceback.format_exc()}"
        print(err, file=sys.stderr)
        try:
            send_line(err[:1800])
        except Exception:
            pass
        sys.exit(1)
