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
import traceback
from datetime import datetime, timezone

import pandas as pd
from pandas.api.types import is_datetime64tz_dtype
import ccxt

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


# ---------- Helpers ----------
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
    เขียนทั้งชีท (replace) เพื่อกัน schema เพี้ยน + ทำ tz-naive เสมอ
    """
    df = _excel_sanitize_datetimes(df)

    # สร้างโฟลเดอร์ปลายทางถ้ายังไม่มี
    os.makedirs(os.path.dirname(path), exist_ok=True)

    mode = "a" if os.path.exists(path) else "w"
    if mode == "a":
        with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name=sheet, index=True)
    else:
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            df.to_excel(writer, sheet_name=sheet, index=True)


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

def _normalize_symbol_to_ccxt(symbol: str) -> str:
    """
    แปลง 'BTCUSDT' -> 'BTC/USDT' (รูปแบบที่ ccxt ต้องการ)
    ถ้าใส่มาเป็น 'BTC/USDT' อยู่แล้วจะคืนค่าเดิม
    """
    if "/" in symbol:
        return symbol
    if symbol.upper().endswith("USDT"):
        base = symbol.upper().replace("USDT", "")
        return f"{base}/USDT"
    return symbol  # เผื่อกรณีอื่น

def _map_tf_to_ccxt(tf: str) -> str:
    """
    map timeframes ให้เข้ากับ ccxt (ใช้ตัวพิมพ์เล็ก)
    """
    tf = tf.lower()
    mapping = {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
        "1d": "1d", "3d": "3d", "1w": "1w", "1mo": "1M", "1mth": "1M",
    }
    return mapping.get(tf, tf)

def fetch_ohlcv_ccxt_binance(symbol: str, timeframe: str = "1d", limit: int = 1000) -> pd.DataFrame:
    """
    ดึง OHLCV สดจาก Binance ผ่าน ccxt → คืน DataFrame คอลัมน์: open, high, low, close, volume
    index เป็น UTC tz‑naive (พร้อมเขียน Excel)
    """
    sym = _normalize_symbol_to_ccxt(symbol)
    tf = _map_tf_to_ccxt(timeframe)

    ex = ccxt.binance({"enableRateLimit": True})
    raw = ex.fetch_ohlcv(sym, timeframe=tf, limit=limit)  # [[ts, o, h, l, c, v], ...]
    if not raw:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    # ทำเป็น UTC tz‑naive แล้วตั้ง index
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
    df = df.set_index("timestamp")
    # ให้ชนกับ schema ในโปรเจกต์ (ถ้าต้องการคอลัมน์ครบ)
    return df[["open", "high", "low", "close", "volume"]]


# ---------- Main ----------
def main() -> None:
    print(f"[{_now_utc_str()}] Start daily BTC analysis job")

    # 1) โหลดราคาสด (ไม่ส่ง xlsx_path) → 1D ล่าสุดเต็มช่วง
    print("• Fetching fresh OHLCV from provider (1D)…")
df_1d = get_data(SYMBOL, TF)

# --- Fallback: ถ้า get_data ว่าง → ไป ccxt/binance ทันที ---
if df_1d is None or len(df_1d) == 0:
    print("• get_data returned empty → fallback to ccxt/binance …")
    # ลองทั้ง "1D" และ "1d" เผื่อ mapping
    for tf_try in (TF, TF.lower()):
        df_1d = fetch_ohlcv_ccxt_binance(SYMBOL, tf_try, limit=1500)
        if len(df_1d) > 0:
            print(f"• ccxt fetched: rows={len(df_1d)} timeframe={tf_try}")
            break

if df_1d is None or len(df_1d) == 0:
    raise RuntimeError("get_data() returned empty df (and ccxt fallback also empty)")


    # 2) อัปเดต historical.xlsx (ชีท: BTCUSDT_1D) ให้เป็นข้อมูลล่าสุดเสมอ
    sheet_name = f"{SYMBOL}_{TF}"
    print(f"• Writing latest data to {HIST_PATH} (sheet: {sheet_name}) … rows={len(df_1d)}")
    save_df_to_excel(df_1d, HIST_PATH, sheet_name)

    # 3) วิเคราะห์จากไฟล์เดียวกัน (ให้ pipeline อื่นอ้างอิงสอดคล้อง)
    print("• Analyzing wave/summary from historical.xlsx …")
    payload = analyze_wave(SYMBOL, TF, xlsx_path=HIST_PATH)
    brief = build_brief_message(payload)

    # 4) สร้างสัญญาณเข้า/ออกตามโปรไฟล์ (ใช้ df จาก payload ถ้ามี)
    print("• Building trade suggestion …")
    df_for_trade = {}
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
    has_entry = False
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
