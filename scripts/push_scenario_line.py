# [ไฟล์] scripts/push_scenario_line.py  (ไฟล์ใหม่)
from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

import requests

# 1) reuse engine + brief builder
from scripts.scenario_engine import build_output
from app.services.wave_service import build_brief_message


LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def _send_line_message(token: str, to: str, text: str) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {
        "to": to,
        "messages": [{"type": "text", "text": text}],
    }
    resp = requests.post(LINE_PUSH_URL, headers=headers, data=json.dumps(payload))
    return resp


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Push scenario summary to LINE")
    p.add_argument("--symbol", default="BTCUSDT", help="เช่น BTCUSDT/ETHUSDT")
    p.add_argument("--rows", type=int, default=600, help="จำกัดจำนวนแถวท้าย (tail)")
    p.add_argument("--dry", action="store_true", help="แค่พิมพ์ข้อความ ไม่ส่ง LINE")
    p.add_argument("--to", default=os.getenv("LINE_TO"), help="LINE userId/roomId/groupId (override ENV LINE_TO)")
    p.add_argument(
        "--token",
        default=os.getenv("CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN"),
        help="LINE channel access token (override ENV CHANNEL_ACCESS_TOKEN)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # สร้างผลลัพธ์ (รวม 1H/4H/1D)
    result = build_output(args.symbol, args.rows)
    msg = build_brief_message(result)

    if args.dry:
        print(msg)
        return 0

    if not args.token:
        print("❌ missing CHANNEL_ACCESS_TOKEN (env or --token)", file=sys.stderr)
        print(msg)
        return 2
    if not args.to:
        print("❌ missing LINE_TO (env or --to)", file=sys.stderr)
        print(msg)
        return 2

    try:
        resp = _send_line_message(args.token, args.to, msg)
        if resp.status_code != 200:
            print(f"❌ LINE push failed {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1
        print("✅ LINE push OK")
        return 0
    except Exception as e:
        print(f"❌ Exception: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
