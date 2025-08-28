#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys, os, pathlib, json, subprocess

# ให้ import โปรเจกต์ได้เมื่อรันเป็นสคริปต์
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.layers.mtf_logic import analyze_mtf
from scripts.layers.mtf_config import TFS_DEFAULT

def build_message(summary: str, payload: dict) -> str:
    det = payload.get("details", {})
    def fmt(tf: str) -> str:
        d = det.get(tf, {})
        rsi = d.get("rsi14")
        atr = d.get("atr_pct")
        sig = d.get("signal")
        close = d.get("close")
        t = d.get("time")
        if rsi is None or atr is None:
            return f"{tf}: {sig}"
        return f"{tf}: {sig} | RSI {rsi:.1f} | ATR% {atr*100:.2f} | Close {close:.2f} | {t}"
    lines = [summary, fmt("30M"), fmt("15M"), fmt("5M")]
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser(description="Push MTF (5M/15M/30M) summary to LINE")
    ap.add_argument("symbol", help="เช่น BTCUSDT")
    ap.add_argument("--tfs", default=",".join(TFS_DEFAULT), help="เช่น 5M,15M,30M")
    ap.add_argument("--send", action="store_true", help="ส่งผ่าน LINE ด้วย scripts/send_line_message.py")
    ap.add_argument("--to", default=os.getenv("LINE_TO"), help="LINE target id (หรือเซ็ต env LINE_TO ไว้)")
    ap.add_argument("--json-out", action="store_true", help="พิมพ์ JSON payload เพิ่มท้าย")
    args = ap.parse_args()

    tfs = tuple(x.strip().upper() for x in args.tfs.split(",") if x.strip())
    summary, payload = analyze_mtf(args.symbol, tfs=tfs)
    msg = build_message(summary, payload)

    print(msg)
    if args.json_out:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.send:
        if not args.to:
            print("⚠️  ต้องระบุ --to หรือกำหนด env LINE_TO ก่อนส่ง", file=sys.stderr)
            sys.exit(2)
        # เรียกสคริปต์ส่ง LINE แบบ argument list (กันปัญหา quoting)
        cmd = [sys.executable, "scripts/send_line_message.py", "--to", args.to, "--text", msg]
        try:
            subprocess.run(cmd, check=True)
            print("✅ sent via LINE")
        except FileNotFoundError:
            print("⚠️  ไม่พบ scripts/send_line_message.py", file=sys.stderr)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"⚠️  LINE command failed: {e}", file=sys.stderr)
            sys.exit(e.returncode)

if __name__ == "__main__":
    main()
