from __future__ import annotations
import os, time
from typing import List, Dict, Any
from pathlib import Path

import schedule
import pandas as pd
import requests
from dotenv import load_dotenv

# โหลด .env จากรากโปรเจกต์
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from app.services.price_provider_binance import get_ohlcv_ccxt_safe
from app.engine.signal_engine import SignalEngine

TF_LIST = ["5M", "15M", "30M"]

# ---------- LINE push ----------
def _push_via_line_messaging(text: str) -> bool:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    to = os.getenv("LINE_USER_ID")
    if not token or not to:
        return False
    try:
        r = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"to": to, "messages": [{"type": "text", "text": text[:4999]}]},
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False

def _push_via_notifier_line(text: str) -> bool:
    try:
        from app.services import notifier_line as nl  # type: ignore
        if hasattr(nl, "push_text"):
            nl.push_text(text)  # type: ignore
            return True
        if hasattr(nl, "notify"):
            nl.notify(text)  # type: ignore
            return True
    except Exception:
        pass
    return False

def _push_via_line_notify(text: str) -> bool:
    token = os.getenv("LINE_NOTIFY_TOKEN")
    if not token:
        return False
    try:
        r = requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {token}"},
            data={"message": text[:999]},
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False

def push_line(text: str) -> None:
    if _push_via_line_messaging(text): return
    if _push_via_notifier_line(text): return
    if _push_via_line_notify(text): return
    print("[LINE:FALLBACK]", text)

# ---------- Scan logic ----------
def scan_symbol(symbol: str, *, limit: int = 500, confidence_gate: int = 60) -> List[str]:
    msgs: List[str] = []
    engine = SignalEngine(cfg={
        "min_candles": 30,
        "sma_fast": 10,
        "sma_slow": 30,
        "risk_pct": 0.01,  # SL ~1%
        "rr": 1.6,         # TP = 1.6R
        "cooldown_sec": 0,
        "move_alerts": [],
    })

    for tf in TF_LIST:
        df: pd.DataFrame = get_ohlcv_ccxt_safe(symbol, tf, limit=limit)
        if df.empty or len(df) < 30:
            continue

        out: Dict[str, Any] = engine.process_ohlcv(symbol, df)
        action = (out.get("action") or "").upper()
        side = out.get("position", {}).get("side", "NONE")
        conf = int(out.get("confidence", 0))

        if (action in {"OPEN", "CLOSE"}) or (conf >= confidence_gate and side != "NONE"):
            last = df.iloc[-1]
            ts = last.get("timestamp")
            close = float(last.get("close", 0.0))
            entry = out.get("position", {}).get("entry")
            tp = out.get("position", {}).get("tp")
            sl = out.get("position", {}).get("sl")
            reason = out.get("reason", "")

            msg = (
                f"🟢 Signal Detected\n"
                f"Symbol: {symbol}\nTF: {tf}\n"
                f"Time: {ts}\nClose: {close:,.2f}\n"
                f"Action: {action}  Side: {side}\n"
                f"Entry: {entry}  TP: {tp}  SL: {sl}\n"
                f"Confidence: {conf}  Reason: {reason}"
            )
            msgs.append(msg)
    return msgs

def run_once():
    # อ่านรายการสัญลักษณ์จาก .env (เช่น "BTCUSDT,ETHUSDT,SOLUSDT")
    symbols = os.getenv("MTA_SYMBOLS", "BTCUSDT").replace(" ", "")
    syms = [s for s in symbols.split(",") if s]
    print(f"[SCAN] symbols={syms} on {', '.join(TF_LIST)}")

    for sym in syms:
        try:
            msgs = scan_symbol(sym, limit=500)
            if not msgs:
                print(f"[SCAN] no signal for {sym}")
                continue
            for m in msgs:
                push_line(m)
                print("[PUSHED]", m.splitlines()[0])
        except Exception as e:
            print(f"[ERROR] {sym}: {e}")

def main():
    # เริ่มต้นรันทันที 1 รอบ
    run_once()
    # ตั้ง schedule ทุก 5 นาที
    schedule.every(5).minutes.do(run_once)
    print("✅ Intraday scanner running (every 5 minutes). Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
