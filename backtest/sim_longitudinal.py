#!/usr/bin/env python3
"""
Longitudinal Elliott Rules Simulation (Pure Analysis)
- Iterates through OHLCV data day-by-day (or candle-by-candle)
- Calls `app.analysis.elliott.analyze_elliott` ONLY
- Logs event entries whenever pattern or stage changes
- Outputs: JSONL (full records), CSV (summary), optional Markdown (pretty log)
"""

from __future__ import annotations
import argparse
import json
import sys
import os
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
import numpy as np

# -----------------------------------------------------------------------------
# Import the user's analyzer (Pure Analysis)
# -----------------------------------------------------------------------------
try:
    from app.analysis.elliott import analyze_elliott  # type: ignore
except Exception as e:
    sys.stderr.write(
        "[ERROR] Could not import 'analyze_elliott' from app.analysis.elliott.\n"
        "Make sure you are running inside your project where that module exists.\n"
        f"Underlying import error: {e}\n"
    )
    if __name__ == "__main__":
        sys.exit(1)

def parse_timestamp_col(ts: pd.Series) -> pd.Series:
    if np.issubdtype(ts.dtype, np.number):
        maxv = float(ts.max())
        unit = "ms" if maxv > 10_000_000_000 else "s"
        dt = pd.to_datetime(ts.astype("int64"), unit=unit, utc=True, errors="coerce").dt.tz_convert(None)
    else:
        dt = pd.to_datetime(ts, utc=True, errors="coerce").dt.tz_convert(None)
    if dt.isna().any():
        raise ValueError("Some timestamps could not be parsed. Check 'timestamp' column format.")
    return dt

def get_stage_from_result(res: Dict[str, Any]) -> str:
    stage = None
    cur = res.get("current", {})
    if isinstance(cur, dict):
        stage = cur.get("stage")
    if not stage:
        stage = res.get("wave_label")
    return stage if isinstance(stage, str) and stage else "UNKNOWN"

def make_event(timestamp: pd.Timestamp, event_type: str,
               prev_pattern: str, prev_stage: str,
               new_pattern: str, new_stage: str,
               full_json: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Timestamp": timestamp.isoformat(),
        "Event Type": event_type,
        "Previous State": f"{prev_pattern} -> {prev_stage}",
        "New State": f"{new_pattern} -> {new_stage}",
        "Summary": summary_for_event(event_type, prev_pattern, prev_stage, new_pattern, new_stage),
        "Full JSON Output": full_json,
    }

def summary_for_event(event_type: str, prev_pattern: str, prev_stage: str,
                      new_pattern: str, new_stage: str) -> str:
    if event_type == "INITIAL_DETECTION":
        return f"First non-UNKNOWN detection: {new_pattern} / {new_stage} (per rule match)."
    if event_type == "PATTERN_CHANGE":
        return f"Pattern changed from {prev_pattern} to {new_pattern} (per rule match)."
    if event_type == "STAGE_UPDATE":
        return f"Stage updated from {prev_stage} to {new_stage} within pattern {new_pattern}."
    return "State change recorded."

def run_simulation(csv_path: str, min_candles: int = 50,
                   pivot_left: int = 2, pivot_right: int = 2,
                   max_swings: int = 30) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    df = pd.read_csv(csv_path)
    needed_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    if not needed_cols.issubset({c.strip().lower() for c in df.columns}):
        cols_normalized = {c.strip().lower(): c for c in df.columns}
        remap = {}
        for need in needed_cols:
            if need in cols_normalized:
                remap[cols_normalized[need]] = need
        df = df.rename(columns=remap)
        if not needed_cols.issubset(df.columns):
            raise ValueError(f"CSV must contain columns {sorted(list(needed_cols))}. Got {sorted(list(df.columns))}")

    df["timestamp"] = parse_timestamp_col(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    events: List[Dict[str, Any]] = []
    prev_pattern = "UNKNOWN"
    prev_stage = "UNKNOWN"

    for i in range(min_candles - 1, len(df)):
        slice_df = df.loc[:i, ["high", "low", "close"]].copy()
        res = analyze_elliott(slice_df, pivot_left=pivot_left, pivot_right=pivot_right, max_swings=max_swings)
        pattern = str(res.get("pattern", "UNKNOWN"))
        stage = get_stage_from_result(res)
        ts = df.loc[i, "timestamp"]

        event_type: Optional[str] = None
        if len(events) == 0:
            if pattern != "UNKNOWN" or stage != "UNKNOWN":
                event_type = "INITIAL_DETECTION"
        else:
            if pattern != prev_pattern:
                event_type = "PATTERN_CHANGE"
            elif stage != prev_stage:
                event_type = "STAGE_UPDATE"

        if event_type:
            events.append(make_event(ts, event_type, prev_pattern, prev_stage, pattern, stage, res))

        prev_pattern, prev_stage = pattern, stage

    if events:
        summary_rows = [{
            "timestamp": e["Timestamp"],
            "event_type": e["Event Type"],
            "prev_pattern": e["Previous State"].split(" -> ")[0],
            "prev_stage": e["Previous State"].split(" -> ")[1] if " -> " in e["Previous State"] else "",
            "new_pattern": e["New State"].split(" -> ")[0],
            "new_stage": e["New State"].split(" -> ")[1] if " -> " in e["New State"] else "",
            "summary": e["Summary"],
        } for e in events]
        summary_df = pd.DataFrame(summary_rows)
    else:
        summary_df = pd.DataFrame(columns=["timestamp","event_type","prev_pattern","prev_stage","new_pattern","new_stage","summary"])

    return events, summary_df

def write_jsonl(path: str, events: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

def write_markdown(path: str, events: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write("---\n")
            f.write(f"**Timestamp:** {e['Timestamp']}\n")
            f.write(f"**Event Type:** {e['Event Type']}\n")
            f.write(f"**Previous State:** {e['Previous State']}\n")
            f.write(f"**New State:** {e['New State']}\n")
            f.write(f"**Summary:** {e['Summary']}\n")
            f.write("**Full JSON Output:**\n")
            f.write("```\n")
            f.write(json.dumps(e["Full JSON Output"], ensure_ascii=False, indent=2))
            f.write("\n```\n")

def main():
    p = argparse.ArgumentParser(description="Run pure Elliott rules longitudinal simulation.")
    p.add_argument("--csv", required=True, help="Path to OHLCV CSV with columns: timestamp, open, high, low, close, volume")
    p.add_argument("--min-candles", type=int, default=50, help="Minimum candles before starting the loop (default: 50)")
    p.add_argument("--pivot-left", type=int, default=2, help="Pivot left window for fractals (default: 2)")
    p.add_argument("--pivot-right", type=int, default=2, help="Pivot right window for fractals (default: 2)")
    p.add_argument("--max-swings", type=int, default=30, help="Maximum swings to pass to analyzer (default: 30)")
    p.add_argument("--out", default="events_log.jsonl", help="Output JSONL file (full events)")
    p.add_argument("--summary", default="events_summary.csv", help="Output CSV summary file")
    p.add_argument("--out-md", default=None, help="Optional Markdown output formatted per spec")
    args = p.parse_args()

    events, summary_df = run_simulation(
        csv_path=args.csv,
        min_candles=args.min_candles,
        pivot_left=args.pivot_left,
        pivot_right=args.pivot_right,
        max_swings=args.max_swings,
    )

    for out_path in filter(None, [args.out, args.summary, args.out_md]):
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

    write_jsonl(args.out, events)
    summary_df.to_csv(args.summary, index=False)
    if args.out_md:
        write_markdown(args.out_md, events)

    counts = {}
    for e in events:
        counts[e["Event Type"]] = counts.get(e["Event Type"], 0) + 1

    sys.stdout.write(
        "[DONE] Longitudinal run finished.\n"
        f"  Events JSONL : {os.path.abspath(args.out)}\n"
        f"  Summary CSV  : {os.path.abspath(args.summary)}\n"
        + (f"  Markdown Log : {os.path.abspath(args.out_md)}\n" if args.out_md else "")
        + f"  Event counts : {counts}\n"
    )

if __name__ == "__main__":
    main()
