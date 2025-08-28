#!/usr/bin/env python3
from __future__ import annotations

import os
import argparse
import sys
import httpx

def push_text(user_id: str, text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        print("ERROR: LINE_CHANNEL_ACCESS_TOKEN is missing", file=sys.stderr)
        sys.exit(1)

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]}

    with httpx.Client(timeout=10) as client:
        r = client.post(url, headers=headers, json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"ERROR: LINE push failed: {e.response.text}", file=sys.stderr)
            sys.exit(2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="LINE userId")
    ap.add_argument("--text", required=True, help="message text")
    args = ap.parse_args()
    push_text(args.to, args.text)
    print("OK: pushed")

if __name__ == "__main__":
    main()
