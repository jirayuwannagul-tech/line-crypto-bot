#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys, pathlib
import json

# ให้ import โมดูลในโปรเจกต์ได้เมื่อรันเป็นสคริปต์
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.layers.mtf_logic import analyze_mtf
from scripts.layers.mtf_config import TFS_DEFAULT

def main():
    ap = argparse.ArgumentParser(description="MTF analyzer for 5M/15M/30M")
    ap.add_argument("symbol", help="เช่น BTCUSDT")
    ap.add_argument("--tfs", default=",".join(TFS_DEFAULT), help="เช่น 5M,15M,30M")
    ap.add_argument("--json-only", action="store_true", help="พิมพ์เฉพาะ JSON (ไม่พิมพ์สรุปบรรทัดแรก)")
    args = ap.parse_args()

    tfs = tuple(x.strip().upper() for x in args.tfs.split(",") if x.strip())
    summary, payload = analyze_mtf(args.symbol, tfs=tfs)

    if not args.json_only:
        print(summary)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
