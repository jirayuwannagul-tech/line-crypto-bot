# scripts/analyze_and_push.py
# =============================================================================
# LAYER A) OVERVIEW
# -----------------------------------------------------------------------------
# ใช้เป็น CLI script:
#   - ดึงข้อมูล (ผ่าน engine/service ภายในโปรเจ็กต์)
#   - วิเคราะห์สัญญาณด้วยโปรไฟล์ (baseline/cholak/chinchot)
#   - ส่งข้อความผลลัพธ์ไป LINE (push ถึง user/room/group หรือ broadcast)
#
# ตัวอย่างรัน:
#   python scripts/analyze_and_push.py --symbol BTCUSDT --tf 1D --profile chinchot --to <USER_ID>
#   python scripts/analyze_and_push.py --symbol ETHUSDT --tf 4H --broadcast
#
# ต้องตั้ง ENV:
#   LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
#   (ถ้ามี historical.xlsx คนละที่: HISTORICAL_XLSX_PATH)
# =============================================================================

from __future__ import annotations
import os
import sys
import argparse
import logging

from app.services.signal_service import analyze_and_get_text
from app.adapters.delivery_line import LineDelivery

log = logging.getLogger("analyze_and_push")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# =============================================================================
# LAYER B) ENV & CLIENT
# -----------------------------------------------------------------------------
def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v if v not in (None, "") else default

def _build_line_client() -> LineDelivery:
    access = _env("LINE_CHANNEL_ACCESS_TOKEN")
    secret = _env("LINE_CHANNEL_SECRET")
    if not access or not secret:
        raise RuntimeError("Missing LINE credentials: set LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET")
    return LineDelivery(access, secret)

# =============================================================================
# LAYER C) ARGPARSE (CLI)
# -----------------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze signal and push/broadcast to LINE")
    p.add_argument("--symbol", required=False, default="BTCUSDT", help="Symbol e.g. BTCUSDT")
    p.add_argument("--tf", required=False, default="1D", help="Timeframe e.g. 1H/4H/1D")
    p.add_argument("--profile", required=False, default=os.getenv("STRATEGY_PROFILE", "baseline"),
                   help="Strategy profile: baseline | cholak | chinchot")
    p.add_argument("--to", required=False, help="LINE userId/roomId/groupId for push")
    p.add_argument("--broadcast", action="store_true", help="Broadcast instead of push")
    p.add_argument("--xlsx", required=False, default=_env("HISTORICAL_XLSX_PATH"),
                   help="Override path to historical.xlsx (optional)")
    return p

# =============================================================================
# LAYER D) MAIN FLOW
# -----------------------------------------------------------------------------
def main() -> int:
    args = _build_argparser().parse_args()

    # 1) วิเคราะห์ และสร้างข้อความสรุป
    cfg = {"profile": args.profile}
    text = analyze_and_get_text(args.symbol, args.tf, profile=args.profile, cfg=cfg, xlsx_path=args.xlsx)

    # 2) ส่ง LINE (push หรือ broadcast)
    client = _build_line_client()
    if args.broadcast:
        log.info("Broadcasting: %s %s (profile=%s)", args.symbol, args.tf, args.profile)
        resp = client.broadcast_text(text)
    else:
        to_id = args.to or _env("LINE_DEFAULT_TO")
        if not to_id:
            log.error("Missing --to and LINE_DEFAULT_TO")
            print("ERROR: Missing --to and LINE_DEFAULT_TO", file=sys.stderr)
            return 2
        log.info("Pushing to %s: %s %s (profile=%s)", to_id, args.symbol, args.tf, args.profile)
        resp = client.push_text(to_id, text)

    if not resp.get("ok"):
        log.error("LINE send failed: %s", resp)
        return 1

    log.info("Done.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
