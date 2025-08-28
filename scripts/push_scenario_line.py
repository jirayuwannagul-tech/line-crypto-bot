#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
import sqlite3
from pathlib import Path
from typing import Tuple

# ให้ import app.* ได้แม้รันจากโฟลเดอร์โครงการ
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Core services
from app.services.wave_service import analyze_wave, build_brief_message  # type: ignore
from app.services.notifier_line import push_message  # type: ignore

# Decision & data helpers
from app.settings.alerts import ALERT_RULES  # type: ignore
from app.analysis.timeframes import get_data  # type: ignore
from app.analysis.indicators import apply_indicators  # type: ignore


DB_PATH = "app/data/signals.db"  # กันสแปมเก็บที่นี่


def _ensure_db() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS alerts(
            symbol TEXT NOT NULL,
            tf TEXT NOT NULL,
            last_sent INTEGER NOT NULL,
            PRIMARY KEY(symbol, tf)
        )"""
    )
    con.commit()
    con.close()


def _can_send(symbol: str, tf: str, minutes: int) -> bool:
    """Debounce: ส่งซ้ำได้เมื่อเกิน N นาที"""
    _ensure_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.execute("SELECT last_sent FROM alerts WHERE symbol=? AND tf=?", (symbol, tf))
    row = cur.fetchone()
    now = int(time.time())
    if row and (now - int(row[0])) < minutes * 60:
        con.close()
        return False
    con.execute(
        "INSERT OR REPLACE INTO alerts(symbol, tf, last_sent) VALUES(?,?,?)",
        (symbol, tf, now),
    )
    con.commit()
    con.close()
    return True


def _calc_atr_pct(symbol: str, tf: str, close: float) -> float:
    df = get_data(symbol, tf)
    dfi = apply_indicators(df.copy())
    if close and "atr14" in dfi.columns:
        return float(dfi["atr14"].iloc[-1] / close)
    # fallback: hi-lo ของแท่งล่าสุด
    hi = float(dfi["high"].iloc[-1])
    lo = float(dfi["low"].iloc[-1])
    return (hi - lo) / close if close else 0.0


def _decide(payload: dict) -> Tuple[str, str]:
    """
    คืนผลการตัดสินใจ: ('LONG'|'SHORT'|'LONG*(soft)'|'SHORT*(soft)'|'NO_SIGNAL', note)
    ตามเกณฑ์ใน ALERT_RULES
    """
    p = payload["percent"]
    lv = payload["levels"]
    last = payload["last"]

    close = float(last["close"])
    ema50 = float(lv.get("ema50", 0.0))
    ema200 = float(lv.get("ema200", 0.0))

    weekly_bias = (
        payload.get("levels", {})
        .get("elliott", {})
        .get("current", {})
        .get("weekly_bias")
        or payload.get("meta", {}).get("weekly_bias")
        or "side"
    )

    atr_pct = _calc_atr_pct(payload["symbol"], payload["tf"], close)

    LONG_OK_TREND = (close > ema50) and (ema50 >= ema200) if ALERT_RULES["ema_trend"] else True
    SHORT_OK_TREND = (close < ema50) and (ema50 <= ema200) if ALERT_RULES["ema_trend"] else True
    ATR_OK = atr_pct >= ALERT_RULES["atr_min_pct"]

    long_prob = int(p["up"])
    short_prob = int(p["down"])
    side_prob = int(p["side"])

    def bias_ok(side: str) -> bool:
        if not ALERT_RULES["weekly_guard"]:
            return True
        if weekly_bias == "down" and side == "long":
            return long_prob >= ALERT_RULES["weekly_override"]
        if weekly_bias == "up" and side == "short":
            return short_prob >= ALERT_RULES["weekly_override"]
        return True

    if LONG_OK_TREND and ATR_OK and long_prob >= ALERT_RULES["prob_strong"] and bias_ok("long"):
        return ("LONG", f"prob={long_prob} atr={atr_pct:.4f} weekly={weekly_bias}")
    if SHORT_OK_TREND and ATR_OK and short_prob >= ALERT_RULES["prob_strong"] and bias_ok("short"):
        return ("SHORT", f"prob={short_prob} atr={atr_pct:.4f} weekly={weekly_bias}")

    if LONG_OK_TREND and ATR_OK and long_prob >= ALERT_RULES["prob_soft"] and bias_ok("long"):
        return ("LONG*(soft)", f"prob={long_prob} atr={atr_pct:.4f} weekly={weekly_bias}")
    if SHORT_OK_TREND and ATR_OK and short_prob >= ALERT_RULES["prob_soft"] and bias_ok("short"):
        return ("SHORT*(soft)", f"prob={short_prob} atr={atr_pct:.4f} weekly={weekly_bias}")

    note = (
        f"long={long_prob} down={short_prob} side={side_prob} "
        f"atr={atr_pct:.4f} weekly={weekly_bias} ema50={ema50:.2f} ema200={ema200:.2f} close={close:.2f}"
    )
    return ("NO_SIGNAL", note)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze & push scenario to LINE")
    p.add_argument("--symbol", required=True, help="เช่น BTCUSDT / ETHUSDT")
    p.add_argument("--tf", required=True, help="เช่น 1H, 4H, 1D")
    p.add_argument("--dry", action="store_true", help="พรีวิวอย่างเดียว ไม่ส่ง LINE")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # วิเคราะห์
    payload = analyze_wave(args.symbol, args.tf)
    msg = build_brief_message(payload)

    # พรีวิว
    print("== preview message ==")
    print(msg)

    # ตัดสินใจ + กันสแปม
    signal, note = _decide(payload)
    print(f"== decision == {signal} | {note}")

    if args.dry:
        print("[dry-run] skip sending to LINE")
        return 0

    if signal == "NO_SIGNAL":
        print("[skip] เกณฑ์ไม่ผ่าน — ไม่ส่ง LINE")
        return 0

    if not _can_send(args.symbol, args.tf, ALERT_RULES["debounce_minutes"]):
        print(f"[skip] debounce {ALERT_RULES['debounce_minutes']} นาที — ยังไม่ถึงเวลา")
        return 0

    # ส่ง LINE (อ่าน ENV ภายใน notifier_line: LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID/LINE_TO)
    try:
        ok = push_message(msg)
        if not ok:
            print("❌ push_message() ส่งไม่สำเร็จ — ตรวจ ENV: LINE_CHANNEL_ACCESS_TOKEN + LINE_USER_ID/LINE_TO", file=sys.stderr)
            return 2
        print("✅ LINE push OK")
        return 0
    except Exception as e:
        print(f"❌ Exception while sending LINE: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
