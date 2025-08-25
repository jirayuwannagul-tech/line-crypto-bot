#!/usr/bin/env python3
"""
Trade Signal Generator → LINE Push
รวมผล Elliott + ราคาจริง + Probabilities จาก scenarios.py
เลือกสัญญาณความน่าจะเป็นสูงสุด แล้วส่งเข้า LINE (ถ้าเปิด SEND_TO_LINE=1)
"""

from __future__ import annotations

import os
import sys
import argparse
import requests
from typing import Dict, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv  # โหลด .env อัตโนมัติ

# โหลดตัวแปรจาก .env (ถ้ามี)
load_dotenv()

# === โปรเจกต์ของเรา ===
from app.logic.scenarios import analyze_scenarios
from app.analysis.timeframes import get_data

# ===============================
# Config: TP/SL (fallback เผื่อ profile ไม่ได้กำหนด)
# ===============================
TP_PCTS = [0.03, 0.05, 0.07]
SL_PCT = 0.03


# ===============================
# Utils: ATR% และ Watch Levels
# ===============================
def _atr_pct(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    """
    ATR% = ATR(n) / close ล่าสุด
    """
    if len(df) < n + 1:
        return None
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    trs = []
    for i in range(1, len(df)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = pd.Series(trs).rolling(n).mean().iloc[-1]
    last_close = df["close"].iloc[-1]
    return float(atr / last_close) if last_close else None


def _watch_levels_from_atr(close: float, atr_pct: Optional[float], k: float = 1.5) -> Tuple[Optional[float], Optional[float]]:
    """
    เลเวลเฝ้าดูแบบหยาบ ๆ จาก ATR% (±k*ATR%)
    """
    if atr_pct is None or close is None:
        return None, None
    return close * (1 - k * atr_pct), close * (1 + k * atr_pct)


# ===============================
# LINE Delivery (push message)
# ===============================
def _can_send_line() -> bool:
    return os.getenv("SEND_TO_LINE", "").strip() == "1"


def _line_token() -> str:
    tok = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("ENV LINE_CHANNEL_ACCESS_TOKEN ไม่ถูกตั้งค่า")
    return tok


def _line_to_user() -> str:
    to = os.getenv("LINE_USER_ID", "").strip()
    if not to:
        raise RuntimeError("ENV LINE_USER_ID ไม่ถูกตั้งค่า")
    return to


def _push_line_text(text: str, to_user: Optional[str] = None) -> None:
    """
    ส่งข้อความเข้า LINE ด้วย push API
    """
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {_line_token()}",
        "Content-Type": "application/json",
    }
    body = {
        "to": to_user or _line_to_user(),
        "messages": [{"type": "text", "text": text}],
    }
    r = requests.post(url, headers=headers, json=body, timeout=10)
    if r.status_code >= 300:
        raise RuntimeError(f"LINE push error {r.status_code}: {r.text}")


# ===============================
# Message Builder (ฟอร์แมตอ่านง่าย)
# ===============================
def _format_line_message(
    symbol: str,
    tf: str,
    result: Dict,
    last_close: float,
    atr_pct: Optional[float],
    watch_dn: Optional[float],
    watch_up: Optional[float],
) -> str:
    """
    result ควรมี: result["probs"] = {"UP": x, "DOWN": y, "SIDE": z}
                  result["best"] = {"direction": "UP"/"DOWN"/"SIDE", "reason": "..."}
                  result["targets"] (อาจมี), result["stop"] (อาจมี)
    โค้ดนี้พยายามทนทาน ถ้า key บางอันไม่มีจะข้ามอย่างสุภาพ
    """
    probs = result.get("probs", {})
    best = result.get("best", {}) or {}
    direction = best.get("direction", "?")
    reason = best.get("reason", "")
    targets = result.get("targets", []) or []
    stop = result.get("stop", None)

    # ถ้าไม่มี targets/stop ลอง fallback เป็น % มาตรฐาน
    if not targets and last_close:
        targets = [
            round(last_close * (1 + p), 2) if direction == "UP" else round(last_close * (1 - p), 2)
            for p in TP_PCTS
        ]
    if stop is None and last_close:
        stop = round(last_close * (1 - SL_PCT), 2) if direction == "UP" else round(last_close * (1 + SL_PCT), 2)

    lines = []
    lines.append("🧠 Signal Alert")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 {symbol} • TF {tf}")
    lines.append(f"💵 ราคาล่าสุด: {last_close:,.2f}")
    lines.append("")

    if probs:
        # แสดง % แบบแบ่งบรรทัดชัดเจน
        up = probs.get("UP", "-")
        dn = probs.get("DOWN", "-")
        sd = probs.get("SIDE", "-")
        lines.append("📈 ความน่าจะเป็น")
        lines.append(f"  ⬆️ UP:   {up}%")
        lines.append(f"  ⬇️ DOWN: {dn}%")
        lines.append(f"  ➡️ SIDE: {sd}%")
        lines.append("")

    lines.append(f"🎯 แผนหลัก: {direction}")
    if reason:
        lines.append(f"📝 เหตุผล: {reason}")

    if targets:
        lines.append("🎯 Targets:")
        for i, t in enumerate(targets, 1):
            lines.append(f"  TP{i}: {t:,.2f}")
    if stop:
        lines.append(f"🛑 Stop Loss: {stop:,.2f}")

    if atr_pct is not None:
        lines.append(f"📏 ATR≈{atr_pct*100:.2f}%")
    if watch_dn and watch_up:
        lines.append(f"🔭 Watch zone: {watch_dn:,.2f} ↔ {watch_up:,.2f}")

    lines.append("")
    lines.append("※ ไม่ใช่คำแนะนำการลงทุน")

    return "\n".join(lines)


# ===============================
# Main
# ===============================
def main():
    parser = argparse.ArgumentParser(description="Generate trade signal and optionally push to LINE.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--tf", default="1D")
    parser.add_argument("--profile", default="baseline")  # เผื่อใช้ภายหลัง แม้ตอนนี้ยังไม่ส่งเข้า cfg
    parser.add_argument("--to", default="", help="LINE User ID (override LINE_USER_ID)")
    args = parser.parse_args()

    # 1) ดึงข้อมูลราคา
    df = get_data(args.symbol, args.tf)
    if df is None or df.empty:
        print("ERROR: ไม่พบข้อมูลราคา")
        sys.exit(1)

    last_close = float(df["close"].iloc[-1])
    atrp = _atr_pct(df, n=14)
    wdn, wup = _watch_levels_from_atr(last_close, atrp, k=1.5)

    # 2) วิเคราะห์ scenarios
    #    ผลลัพธ์คาดหวัง: dict ที่มี probs/best/targets/stop เป็นต้น
    result = analyze_scenarios(df=df, symbol=args.symbol, tf=args.tf)

    # 3) สร้างสรุปข้อความ (สวย/อ่านง่าย)
    text = _format_line_message(
        symbol=args.symbol,
        tf=args.tf,
        result=result,
        last_close=last_close,
        atr_pct=atrp,
        watch_dn=wdn,
        watch_up=wup,
    )

    # 4) พิมพ์ในเทอร์มินัลเสมอ
    print("\n" + "=" * 8 + " SIGNAL " + "=" * 8)
    print(text)
    print("=" * 24 + "\n")

    # 5) ส่งเข้า LINE ถ้าเปิดใช้
    if _can_send_line():
        try:
            to_user = args.to.strip() or None
            _push_line_text(text, to_user=to_user)
            print("✅ Pushed to LINE")
        except Exception as e:
            print(f"❌ LINE push failed: {e}")
            sys.exit(2)


if __name__ == "__main__":
    main()
