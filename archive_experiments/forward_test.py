# scripts/forward_test.py
from __future__ import annotations
import argparse, os
import pandas as pd
import numpy as np

# ใช้สูตรอินดิเคเตอร์จาก RULES layer
from app.analysis.indicators import apply_indicators

# -----------------------------
# IO: โหลด CSV ราคา
# -----------------------------
def load_price(symbol: str, tf: str) -> pd.DataFrame:
    candidates = [
        f"data/{symbol}_{tf}.csv",
        f"app/data/{symbol}_{tf}.csv",
    ]
    for p in candidates:
        if os.path.exists(p):
            df = pd.read_csv(p)
            lower2orig = {c.lower(): c for c in df.columns}

            def pick(*names):
                for n in names:
                    if n in lower2orig: return lower2orig[n]
                return None

            time_col = pick("time", "timestamp", "open_time", "date", "datetime")
            if not time_col:
                raise KeyError(f"No time column in {p}. columns={list(df.columns)}")

            rename_map = {time_col: "time"}
            for k in ("open","high","low","close","volume","vol"):
                if k in lower2orig:
                    rename_map[lower2orig[k]] = "volume" if k=="vol" else k

            df = df.rename(columns=rename_map)
            need = {"time","open","high","low","close"}
            miss = need - set(df.columns)
            if miss:
                raise KeyError(f"Missing columns {sorted(miss)} in {p}")

            if pd.api.types.is_numeric_dtype(df["time"]):
                unit = "ms" if df["time"].max() > 10**12 else "s"
                df["time"] = pd.to_datetime(df["time"], unit=unit)
            else:
                df["time"] = pd.to_datetime(df["time"], errors="coerce")

            if df["time"].isna().any():
                raise ValueError(f"Failed to parse time in {p}")

            return df.sort_values("time").reset_index(drop=True)
    raise FileNotFoundError(f"CSV for {symbol}_{tf} not found in {candidates}")

# -----------------------------
# คำนวณอินดิเคเตอร์ (เรียก RULES)
# -----------------------------
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = apply_indicators(df)  # เติม ema20/50/200, rsi14, adx14, atr14, ฯลฯ
    return df

# -----------------------------
# Logic Filters → ทิศทางสัญญาณ
# -----------------------------
def decide_direction(row,
                     rsi_bull_min=55.0, rsi_bear_max=45.0,
                     adx_min=25.0) -> str:
    e50, e200, rsi, adx = row["ema50"], row["ema200"], row["rsi14"], row["adx14"]
    if np.isnan(e50) or np.isnan(e200) or np.isnan(rsi) or np.isnan(adx):
        return "FLAT"
    if adx < adx_min:
        return "FLAT"
    if e50 > e200 and rsi >= rsi_bull_min:
        return "LONG"
    if e50 < e200 and rsi <= rsi_bear_max:
        return "SHORT"
    return "FLAT"

# -----------------------------
# Forward Test (รองรับ Trailing + Leverage)
# -----------------------------
def forward_test(df: pd.DataFrame,
                 horizon: int = 48,
                 min_bars: int = 250,
                 rsi_bull_min: float = 55.0,
                 rsi_bear_max: float = 45.0,
                 adx_min: float = 25.0,
                 atr_tp_k: float = 1.5,
                 atr_sl_k: float = 1.0,
                 trail_atr_k: float = 0.0,
                 leverage: float = 1.0):
    """
    - ทิศทาง: ADX/EMA/RSI
    - TP/SL: อิง ATR14 ที่แท่งเข้า
    - Trailing stop: ตาม ATR14 แท่งเข้า (0=ปิด)
    - Leverage: คูณผลกำไร/ขาดทุนเป็น %
    """
    records = []
    start = max(min_bars, 200)  # เผื่อ warm-up EMA200

    for i in range(start, len(df) - horizon):
        row = df.iloc[i]
        direction = decide_direction(
            row,
            rsi_bull_min=rsi_bull_min,
            rsi_bear_max=rsi_bear_max,
            adx_min=adx_min
        )
        px = float(row["close"])
        atr_entry = float(row["atr14"]) if not np.isnan(row["atr14"]) else np.nan

        if direction == "FLAT" or np.isnan(atr_entry):
            records.append({
                "time": row["time"], "close": px, "signal": "FLAT",
                "entry": None, "tp": None, "sl": None, "exit": None,
                "result": "SKIP", "pnl_pct": 0.0, "event": "SKIP",
                "leverage": leverage, "trail_k": trail_atr_k
            })
            continue

        entry = px
        if direction == "LONG":
            tp = entry + atr_tp_k * atr_entry
            sl = entry - atr_sl_k * atr_entry
        else:
            tp = entry - atr_tp_k * atr_entry
            sl = entry + atr_sl_k * atr_entry

        future = df.iloc[i+1:i+1+horizon]

        # เหตุการณ์
        tp_idx = sl_idx = trail_idx = None
        trail_px = None

        if direction == "LONG":
            highest = entry
            for j, r in future.iterrows():
                hi = float(r["high"]); lo = float(r["low"])
                if tp_idx is None and hi >= tp: tp_idx = j
                if sl_idx is None and lo <= sl: sl_idx = j
                if trail_atr_k > 0.0:
                    highest = max(highest, hi)
                    cur_trail = highest - trail_atr_k * atr_entry
                    if trail_idx is None and lo <= cur_trail:
                        trail_idx = j; trail_px = cur_trail
                if tp_idx is not None or sl_idx is not None or trail_idx is not None:
                    break
        else:  # SHORT
            lowest = entry
            for j, r in future.iterrows():
                hi = float(r["high"]); lo = float(r["low"])
                if tp_idx is None and lo <= tp: tp_idx = j
                if sl_idx is None and hi >= sl: sl_idx = j
                if trail_atr_k > 0.0:
                    lowest = min(lowest, lo)
                    cur_trail = lowest + trail_atr_k * atr_entry
                    if trail_idx is None and hi >= cur_trail:
                        trail_idx = j; trail_px = cur_trail
                if tp_idx is not None or sl_idx is not None or trail_idx is not None:
                    break

        # ตัดสินผลตามเหตุการณ์แรก
        exit_px = future.iloc[-1]["close"] if len(future) else entry
        event = "EXPIRY"
        if any(idx is not None for idx in (tp_idx, sl_idx, trail_idx)):
            earliest_idx = min([idx for idx in (tp_idx, sl_idx, trail_idx) if idx is not None])
            if earliest_idx == tp_idx:
                exit_px = tp; event = "TP"; result = "WIN"
            elif earliest_idx == sl_idx:
                exit_px = sl; event = "SL"; result = "LOSS"
            else:
                exit_px = trail_px if trail_px is not None else exit_px
                event = "TRAIL"
                side = 1.0 if direction == "LONG" else -1.0
                result = "WIN" if side * (exit_px - entry) > 0 else ("LOSS" if side * (exit_px - entry) < 0 else "NEUTRAL")
        else:
            if direction == "LONG":
                result = "WIN" if exit_px > entry else ("LOSS" if exit_px < entry else "NEUTRAL")
            else:
                result = "WIN" if exit_px < entry else ("LOSS" if exit_px > entry else "NEUTRAL")

        side = 1.0 if direction == "LONG" else -1.0
        pnl_pct = (exit_px - entry) / entry * 100.0 * side * float(leverage)

        records.append({
            "time": row["time"],
            "close": px,
            "signal": direction,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "exit": float(exit_px),
            "result": result,
            "event": event,
            "pnl_pct": round(float(pnl_pct), 4),
            "leverage": float(leverage),
            "trail_k": float(trail_atr_k),
        })

    res = pd.DataFrame(records)
    if res.empty:
        return res, {
            "total": 0, "win": 0, "loss": 0, "neutral": 0, "skip": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0, "max_dd": 0.0
        }

    # Equity (สะสม %)
    res["equity_pct"] = res["pnl_pct"].cumsum()

    # KPI
    closed = res["result"].isin(["WIN","LOSS","NEUTRAL"])
    total   = int(closed.sum())
    win     = int((res["result"]=="WIN").sum())
    loss    = int((res["result"]=="LOSS").sum())
    neutral = int((res["result"]=="NEUTRAL").sum())
    skip    = int((res["result"]=="SKIP").sum())

    wins = res.loc[res["result"]=="WIN", "pnl_pct"]
    losses = -res.loc[res["result"]=="LOSS", "pnl_pct"]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    profit_factor = (wins.sum()/max(1e-9, losses.sum())) if len(losses) else float("inf")
    win_rate = win / max(1, (win + loss)) * 100.0
    expectancy = (win_rate/100.0)*avg_win - (1 - win_rate/100.0)*avg_loss

    # Max Drawdown
    eq = res["equity_pct"].ffill().fillna(0.0).values
    peak = -1e9; max_dd = 0.0
    for v in eq:
        if v > peak: peak = v
        dd = peak - v
        if dd > max_dd: max_dd = dd

    summary = {
        "total": total, "win": win, "loss": loss, "neutral": neutral, "skip": skip,
        "win_rate": round(win_rate, 2),
        "avg_win": round(avg_win, 3),
        "avg_loss": round(avg_loss, 3),
        "profit_factor": round(profit_factor, 3) if np.isfinite(profit_factor) else float("inf"),
        "expectancy": round(expectancy, 3),
        "max_dd": round(max_dd, 3),
    }
    return res, summary

# -----------------------------
# CLI
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Forward Test (ADX/EMA/RSI + ATR TP/SL)")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="1H", choices=["1D","4H","1H"])
    ap.add_argument("--start", default=None)  # YYYY-MM-DD
    ap.add_argument("--end", default=None)    # YYYY-MM-DD
    ap.add_argument("--horizon", type=int, default=48)
    ap.add_argument("--min-bars", type=int, default=250)
    ap.add_argument("--adx-min", type=float, default=25.0)
    ap.add_argument("--rsi-bull-min", type=float, default=55.0)
    ap.add_argument("--rsi-bear-max", type=float, default=45.0)
    ap.add_argument("--atr-tp-k", type=float, default=1.5)
    ap.add_argument("--atr-sl-k", type=float, default=1.0)
    ap.add_argument("--trail-atr-k", type=float, default=0.0, help="Trailing stop = k*ATR (0=ปิด)")
    ap.add_argument("--leverage", type=float, default=1.0, help="คูณผลลัพธ์กำไร/ขาดทุนเป็น %")
    ap.add_argument("--out", default="output/forward_atr_results.csv")
    ap.add_argument("--no-plots", action="store_true", help="ข้ามการวาดกราฟ")
    args = ap.parse_args()

    df_all = load_price(args.symbol, args.tf)
    if args.start: df_all = df_all[df_all["time"] >= pd.to_datetime(args.start)]
    if args.end:   df_all = df_all[df_all["time"] <= pd.to_datetime(args.end)]
    df_all = df_all.reset_index(drop=True)
    print(f"[DEBUG] Loaded window bars: {len(df_all)}  start={df_all['time'].iloc[0] if len(df_all) else 'NA'}  end={df_all['time'].iloc[-1] if len(df_all) else 'NA'}")

    if len(df_all) == 0:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        pd.DataFrame().to_csv(args.out, index=False); print(f"[WARN] Empty window -> {args.out}"); return

    df = add_indicators(df_all)
    need = max(args.min_bars, 200) + args.horizon + 1
    if len(df) < need:
        print(f"[WARN] Not enough bars (have {len(df)}, need >= {need}). Continue anyway.")

    res, summary = forward_test(
        df,
        horizon=args.horizon,
        min_bars=args.min_bars,
        rsi_bull_min=args.rsi_bull_min,
        rsi_bear_max=args.rsi_bear_max,
        adx_min=args.adx_min,
        atr_tp_k=args.atr_tp_k,
        atr_sl_k=args.atr_sl_k,
        trail_atr_k=args.trail_atr_k,
        leverage=args.leverage,
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    res.to_csv(args.out, index=False)
    print("=== Forward Test Summary ===")
    print(f"Symbol/TF       : {args.symbol}/{args.tf}")
    print(f"Bars/Window     : {len(df)}")
    print(f"Horizon/MinBars : {args.horizon} / {args.min_bars}")
    print(f"ADX/RSI         : min={args.adx_min} | bull_min={args.rsi_bull_min} | bear_max={args.rsi_bear_max}")
    print(f"ATR TP/SL k     : {args.atr_tp_k} / {args.atr_sl_k}")
    print(f"Trail ATR k     : {args.trail_atr_k}")
    print(f"Leverage        : {args.leverage}x")
    for k, v in summary.items():
        print(f"{k:14s}: {v}")
    print(f"Saved CSV       : {args.out}")

    # ===== Reports (KPI JSON + Monthly breakdown + Plots) =====
    # KPI
    kpi_out = "output/kpi_summary.json"
    wins = res.loc[res["result"]=="WIN","pnl_pct"]
    losses = -res.loc[res["result"]=="LOSS","pnl_pct"]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    profit_factor = (wins.sum()/max(1e-9, losses.sum())) if len(losses) else float("inf")
    win_rate = summary["win_rate"]
    expectancy = (win_rate/100.0)*avg_win - (1 - win_rate/100.0)*avg_loss
    # Max DD บน equity_pct
    eq = res["pnl_pct"].cumsum()
    peak = eq.cummax()
    max_dd = float((peak - eq).max())
    import json
    with open(kpi_out, "w") as f:
        json.dump({
            **summary,
            "avg_win_pct": round(avg_win,3),
            "avg_loss_pct": round(avg_loss,3),
            "profit_factor": (round(profit_factor,3) if np.isfinite(profit_factor) else "inf"),
            "expectancy_pct": round(expectancy,3),
            "max_drawdown_pct": round(max_dd,3)
        }, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] {kpi_out}")

    # Monthly breakdown
    mb_out = "output/monthly_breakdown.csv"
    md = res.copy()
    md["time"] = pd.to_datetime(md["time"])
    md["yyyy_mm"] = md["time"].dt.to_period("M").astype(str)
    g = md.groupby("yyyy_mm")
    mb = pd.DataFrame({
        "trades": g["result"].apply(lambda s: s.isin(["WIN","LOSS","NEUTRAL"]).sum()),
        "wins": (g["result"].apply(lambda s: (s=="WIN").sum())),
        "losses": (g["result"].apply(lambda s: (s=="LOSS").sum())),
        "neutral": (g["result"].apply(lambda s: (s=="NEUTRAL").sum())),
        "skips": (g["result"].apply(lambda s: (s=="SKIP").sum())),
        "win_rate_pct": (g["result"].apply(lambda s: (s=="WIN").sum()) /
                         (g["result"].apply(lambda s: ((s=="WIN")|(s=="LOSS")).sum()).replace(0,1)) * 100.0),
        "sum_pnl_pct": g["pnl_pct"].sum(),
        "equity_end_pct": g["pnl_pct"].sum().cumsum()
    }).reset_index()
    mb.to_csv(mb_out, index=False)
    print(f"[SAVED] {mb_out}")

    # Plots
    if not args.no_plots:
        import matplotlib.pyplot as plt
        # Equity curve (by trade)
        eq_png = "output/equity_curve.png"
        plt.figure(figsize=(12,5))
        res_sorted = res.copy()
        res_sorted["time"] = pd.to_datetime(res_sorted["time"])
        res_sorted = res_sorted.sort_values("time")
        plt.plot(res_sorted["time"], res_sorted["pnl_pct"].cumsum())
        plt.title("Equity Curve (%)")
        plt.xlabel("Time"); plt.ylabel("Cumulative PnL (%)")
        plt.tight_layout(); plt.savefig(eq_png, dpi=150); plt.close()
        print(f"[SAVED] {eq_png}")

        # Monthly win rate
        winrate_png = "output/monthly_winrate.png"
        plt.figure(figsize=(12,4))
        plt.plot(mb["yyyy_mm"], mb["win_rate_pct"], marker='o')
        plt.title("Monthly Win Rate (%)")
        plt.xlabel("Month"); plt.ylabel("Win Rate (%)")
        plt.xticks(rotation=60); plt.tight_layout()
        plt.savefig(winrate_png, dpi=150); plt.close()
        print(f"[SAVED] {winrate_png}")

        # Monthly equity cumulative
        meq_png = "output/monthly_equity.png"
        plt.figure(figsize=(12,4))
        plt.plot(mb["yyyy_mm"], mb["equity_end_pct"], marker='o')
        plt.title("Monthly Equity (Cumulative %)")
        plt.xlabel("Month"); plt.ylabel("Equity (%)")
        plt.xticks(rotation=60); plt.tight_layout()
        plt.savefig(meq_png, dpi=150); plt.close()
        print(f"[SAVED] {meq_png}")

if __name__ == "__main__":
    main()
