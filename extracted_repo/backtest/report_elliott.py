# backtest/report_elliott.py
# =============================================================================
# Elliott Wave Report
# -----------------------------------------------------------------------------
# - อ่านผลจาก backtest/results_elliott.csv
# - คำนวณ accuracy พื้นฐาน (trend_pred vs real_trend)
# - Metric เสริม:
#   1) Invalid Impulse Rate (% overlap ผิดกฎ)
#   2) Valid Corrective Pattern Rate (ZigZag, Flat, Triangle)
#   3) Accuracy by wave_label (ถ้ามี)
# =============================================================================

import sys
import pandas as pd
import json

def generate_report(file_path="backtest/results_elliott.csv"):
    df = pd.read_csv(file_path)

    required_cols = {"trend_pred", "real_trend", "hit"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError(f"❌ ขาดคอลัมน์จำเป็นใน {file_path}: {missing}")

    # ===== Accuracy พื้นฐาน =====
    total = len(df)
    correct = int(df["hit"].sum())
    accuracy = (correct / total * 100) if total else 0.0

    print("=== 📊 Elliott Wave Backtest Report ===")
    print(f"Signals: {total}")
    print(f"Correct Predictions: {correct}")
    print(f"Accuracy (trend vs next bar): {accuracy:.2f}%")

    # ===== Accuracy แยกตาม trend_pred =====
    if "trend_pred" in df.columns:
        print("\n— Accuracy by trend_pred —")
        for k, g in df.groupby("trend_pred", dropna=False):
            n = len(g)
            hit = int(g["hit"].sum())
            acc = (hit / n * 100) if n else 0.0
            print(f"{str(k):>15}: {acc:.2f}%  (n={n})")

    # ===== Accuracy แยกตาม wave_label (ใหม่) =====
    if "wave_label" in df.columns:
        print("\n— Accuracy by wave_label —")
        for k, g in df.groupby("wave_label", dropna=False):
            n = len(g)
            if "hit" in g.columns:
                hit = int(g["hit"].sum())
                acc = (hit / n * 100) if n else 0.0
                print(f"{str(k):>25}: {acc:.2f}%  (n={n})")
            else:
                print(f"{str(k):>25}: - (no hit col)")

    # ===== Metric เสริม 1: Invalid Impulse Rate =====
    if "debug" in df.columns:
        invalid_impulse = 0
        impulse_total = 0
        for _, row in df.iterrows():
            if row["trend_pred"] and "IMPULSE" in str(row["trend_pred"]).upper():
                impulse_total += 1
                try:
                    dbg = json.loads(row["debug"]) if isinstance(row["debug"], str) else row["debug"]
                    rules = dbg.get("rules", []) if isinstance(dbg, dict) else []
                    for r in rules:
                        if r.get("name", "").startswith("Wave4 does not overlap") and not r.get("passed", True):
                            invalid_impulse += 1
                except Exception:
                    continue
        if impulse_total > 0:
            rate = invalid_impulse / impulse_total * 100
            print(f"\n🚨 Invalid Impulse Rate: {rate:.2f}%  ({invalid_impulse}/{impulse_total})")

    # ===== Metric เสริม 2: Valid Corrective Pattern Rate =====
    corrective_patterns = {"ZIGZAG", "FLAT", "TRIANGLE"}
    valid_counts = {p: 0 for p in corrective_patterns}
    total_counts = {p: 0 for p in corrective_patterns}

    if "debug" in df.columns:
        for _, row in df.iterrows():
            patt = str(row["trend_pred"]).upper()
            if patt in corrective_patterns:
                total_counts[patt] += 1
                try:
                    dbg = json.loads(row["debug"]) if isinstance(row["debug"], str) else row["debug"]
                    rules = dbg.get("rules", []) if isinstance(dbg, dict) else []
                    if all(r.get("passed", False) for r in rules):
                        valid_counts[patt] += 1
                except Exception:
                    continue

    print("\n— Valid Corrective Pattern Rate —")
    for p in corrective_patterns:
        if total_counts[p] > 0:
            rate = valid_counts[p] / total_counts[p] * 100
            print(f"{p:>10}: {rate:.2f}%  ({valid_counts[p]}/{total_counts[p]})")
        else:
            print(f"{p:>10}: - (n=0)")


if __name__ == "__main__":
    file = sys.argv[1] if len(sys.argv) > 1 else "backtest/results_elliott.csv"
    generate_report(file)
