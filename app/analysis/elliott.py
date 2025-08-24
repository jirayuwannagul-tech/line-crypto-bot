# app/analysis/elliott.py
# -----------------------------------------------------------------------------
# Basic Elliott Wave Analyzer (rule-based, heuristic)
# Returns a compact payload for downstream use:
#   {
#     "pattern": "IMPULSE|DIAGONAL|ZIGZAG|FLAT|TRIANGLE|DOUBLE_THREE|TRIPLE_THREE|UNKNOWN",
#     "completed": bool,
#     "current": {"stage": "...", "direction": "up|down|side"},
#     "next": {"stage": "...", "direction": "up|down|side"},
#     "targets": {"key": float, ...},          # fibonacci-based objective levels
#     "debug": { "swings": DataFrame-like, ... }  # minimal debug info (safe to ignore)
#   }
#
# Notes:
# - Uses fractal pivots to extract swing points, then tries to fit patterns.
# - Enforces Elliott hard rules for Impulse (with fallback to Diagonal when overlap).
# - Corrective patterns handled: Zigzag (5-3-5), Flat (3-3-5), Triangle (3-3-3-3-3).
# - Composite corrections (placeholders): Double Three (W-X-Y), Triple Three (W-X-Y-X-Z).
# - Targets are heuristic Fibo projections suitable as starting points for orchestration.
# - This is intentionally conservative to avoid false “Impulse” labels.
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

# =============================================================================
# Tunable thresholds (ช่วยให้จูนได้ภายหลัง)
# =============================================================================
# เกณฑ์ "breakout" ของ wave5 เมื่อเทียบปลาย wave3 (คิดเป็นสัดส่วนของ median(w1,w3,w5))
IMPULSE_TOP_BREAKOUT_FACTOR: float = 0.30
# เกณฑ์ "ขนาดของ wave5" ขั้นต่ำเทียบกับคลื่น motive ที่สั้นกว่าใน (w1,w3)
IMPULSE_W5_MIN_RATIO: float = 0.60

Direction = Literal["up", "down", "side"]
Pattern = Literal[
    "IMPULSE",
    "DIAGONAL",
    "ZIGZAG",
    "FLAT",
    "TRIANGLE",
    "DOUBLE_THREE",
    "TRIPLE_THREE",
    "UNKNOWN",
]

__all__ = ["analyze_elliott", "Pattern", "Direction"]


# =============================================================================
# Utilities: pivots & swings
# =============================================================================

def _fractals(df: pd.DataFrame, left: int = 2, right: int = 2) -> Tuple[pd.Series, pd.Series]:
    """Boolean Series for swing high / swing low via simple fractal logic."""
    high = df["high"].values
    low = df["low"].values
    n = len(df)

    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)

    for i in range(left, n - right):
        win_h = high[i - left : i + right + 1]
        win_l = low[i - left : i + right + 1]
        if np.argmax(win_h) == left and high[i] == win_h.max():
            sh[i] = True
        if np.argmin(win_l) == left and low[i] == win_l.min():
            sl[i] = True
    return pd.Series(sh, index=df.index), pd.Series(sl, index=df.index)


def _build_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Return ordered swings with columns: ['idx','timestamp','price','type'] where type in {'H','L'}."""
    is_sh, is_sl = _fractals(df, left=left, right=right)
    rows: List[Dict[str, object]] = []
    for i in range(len(df)):
        if is_sh.iat[i]:
            rows.append({
                "idx": i,
                "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i],
                "price": float(df["high"].iat[i]),
                "type": "H",
            })
        if is_sl.iat[i]:
            rows.append({
                "idx": i,
                "timestamp": df.index[i] if "timestamp" not in df.columns else df["timestamp"].iat[i],
                "price": float(df["low"].iat[i]),
                "type": "L",
            })

    # ✅ ต้องเช็คก่อนสร้าง DataFrame และก่อน sort เสมอ
    if not rows:
        return pd.DataFrame(columns=["idx", "timestamp", "price", "type"])

    sw = pd.DataFrame.from_records(rows)

    # กันกรณีผิดปกติที่ไม่มีคีย์ 'idx' ในแถวใดแถวหนึ่ง
    if "idx" not in sw.columns:
        return pd.DataFrame(columns=["idx", "timestamp", "price", "type"])

    sw = sw.sort_values("idx").reset_index(drop=True)

    # enforce alternation by removing duplicates in succession (keep more extreme)
    cleaned: List[Dict[str, object]] = []
    for r in sw.to_dict("records"):
        if not cleaned:
            cleaned.append(r)
            continue
        if cleaned[-1]["type"] == r["type"]:
            if r["type"] == "H":
                if r["price"] >= cleaned[-1]["price"]:
                    cleaned[-1] = r
            else:  # "L"
                if r["price"] <= cleaned[-1]["price"]:
                    cleaned[-1] = r
        else:
            cleaned.append(r)
    return pd.DataFrame(cleaned)


def _leg_len(a: float, b: float) -> float:
    return abs(b - a)


def _retracement_ratio(a0: float, a1: float, b: float) -> Optional[float]:
    """
    Retracement of leg A (a0->a1) by point b (end of B).
    For up A: ratio = (a1 - b) / (a1 - a0)
    For down A: ratio = (b - a1) / (a0 - a1)
    """
    if a1 == a0:
        return None
    if a1 > a0:  # up
        return (a1 - b) / (a1 - a0)
    else:  # down
        return (b - a1) / (a0 - a1)


def _ratio(val: float, base: float) -> Optional[float]:
    if base == 0:
        return None
    return abs(val) / abs(base)


def _dir(a: float, b: float) -> Direction:
    if b > a: return "up"
    if b < a: return "down"
    return "side"


# =============================================================================
# Pattern detectors (heuristic, rule-checked)
# =============================================================================

@dataclass
class DetectResult:
    pattern: Pattern
    completed: bool
    current_stage: str
    next_stage: str
    direction: Direction
    targets: Dict[str, float]
    meta: Dict[str, object]


def _detect_impulse(sw: pd.DataFrame, allow_diagonal: bool = True) -> Optional[DetectResult]:
    """
    Try to fit last 6 alternating swings to an impulse (1-2-3-4-5).
    Rules checked:
      - Wave2 does not retrace beyond start of Wave1
      - Wave3 not the shortest among motive (1,3,5)
      - Wave4 does not overlap Wave1 price territory (if overlaps -> DIAGONAL if allowed)
    """
    if len(sw) < 6:
        return None

    # Iterate windows from most recent backwards to find a valid fit
    for end in range(len(sw), 5, -1):
        win = sw.iloc[end - 6 : end]  # 6 points -> 5 waves
        types = win["type"].tolist()
        prices = win["price"].tolist()
        idxs = win["idx"].tolist()

        # Valid alternation must end with same extreme type as wave5:
        # Up impulse ends at H (L-H-L-H-L-H); Down impulse ends at L (H-L-H-L-H-L)
        if types not in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
            continue

        direction = "up" if types[-1] == "H" else "down"

        p0, p1, p2, p3, p4, p5 = prices
        # Legs
        w1 = _leg_len(p0, p1)
        w2 = _leg_len(p1, p2)
        w3 = _leg_len(p2, p3)
        w4 = _leg_len(p3, p4)
        w5 = _leg_len(p4, p5)

        # ---- Rule 1: Wave2 not beyond Wave1 start
        if direction == "up":
            if p2 <= p0:  # retraced below start of W1
                continue
        else:
            if p2 >= p0:
                continue

        # ---- Rule 2: Wave3 not the shortest among (1,3,5)
        motive_lengths = [w1, w3, w5]
        if w3 < min(w1, w5):
            continue

        # ---- Rule 3: Wave4 overlap Wave1 territory?
        overlap = False
        if direction == "up":
            # wave4 low must be above wave1 high (no overlap)
            if p4 <= p1:
                overlap = True
        else:
            # wave4 high must be below wave1 low
            if p4 >= p1:
                overlap = True

        if overlap and not allow_diagonal:
            continue

        # =============================================================================
        # Completion heuristic (แยก progress vs top):
        # ใช้สองเกณฑ์: (1) breakout ของ wave5 เทียบปลาย wave3, (2) ขนาดของ w5 เทียบ w1,w3
        # =============================================================================
        motive_med = float(np.median([w1, w3, max(w5, 1e-9)]))
        if direction == "up":
            breakout = max(0.0, p5 - p3)
        else:
            breakout = max(0.0, p3 - p5)
        break_ok = breakout >= IMPULSE_TOP_BREAKOUT_FACTOR * motive_med
        w5_ok    = w5 >= IMPULSE_W5_MIN_RATIO * min(w1, w3)

        if break_ok and w5_ok:
            # === เคสถึงยอดแล้ว (TOP/DIAGONAL TOP) ===
            completed = True
            current_stage = "impulse_5_complete"
            next_stage = "corrective_A" if direction == "up" else "corrective_A_down"

            # Targets for the NEXT move (post-impulse correction) using fib retrace of wave (0->5)
            total_len = abs(p5 - p0)
            if direction == "up":
                t_382 = p5 - total_len * 0.382
                t_500 = p5 - total_len * 0.500
                t_618 = p5 - total_len * 0.618
                targets = {
                    "post_impulse_retrace_38.2%": float(t_382),
                    "post_impulse_retrace_50%": float(t_500),
                    "post_impulse_retrace_61.8%": float(t_618),
                }
            else:
                t_382 = p5 + total_len * 0.382
                t_500 = p5 + total_len * 0.500
                t_618 = p5 + total_len * 0.618
                targets = {
                    "post_impulse_retrace_38.2%": float(t_382),
                    "post_impulse_retrace_50%": float(t_500),
                    "post_impulse_retrace_61.8%": float(t_618),
                }
        else:
            # === เคสยัง "IMPULSE กำลังดำเนิน" (PROGRESS) ===
            completed = False
            current_stage = "impulse_progress"
            next_stage = "impulse_5_in_progress"

            # Targets: โปรเจคชั่น wave5 ต่อจาก p4 (100%–161.8% ของ w1)
            base = max(w1, 1e-9)
            proj_100 = 1.00 * base
            proj_1618 = 1.618 * base
            if direction == "up":
                targets = {
                    "wave5_projection_100%": float(p4 + proj_100),
                    "wave5_projection_161.8%": float(p4 + proj_1618),
                }
            else:
                targets = {
                    "wave5_projection_100%": float(p4 - proj_100),
                    "wave5_projection_161.8%": float(p4 - proj_1618),
                }

        patt: Pattern = "IMPULSE"
        if overlap:
            patt = "DIAGONAL"

        return DetectResult(
            pattern=patt,
            completed=completed,
            current_stage=current_stage,
            next_stage=next_stage,
            direction=direction,
            targets=targets,
            meta={
                "window_indices": idxs,
                "window_types": types,
                "window_prices": prices,
                "overlap": overlap,
                "legs": {"w1": w1, "w2": w2, "w3": w3, "w4": w4, "w5": w5},
                "completion_metrics": {
                    "breakout": float(breakout),
                    "motive_median": float(motive_med),
                    "break_ok": bool(break_ok),
                    "w5_ok": bool(w5_ok),
                    "BREAKOUT_FACTOR": IMPULSE_TOP_BREAKOUT_FACTOR,
                    "W5_MIN_RATIO": IMPULSE_W5_MIN_RATIO,
                },
            },
        )
    return None


def _detect_zigzag(sw: pd.DataFrame) -> Optional[DetectResult]:
    """
    Zigzag: A-B-C with 5-3-5 spirit (heuristic without internal 5-count)
    Checks:
      - B retraces ~38.2–61.8% of A
      - C length ~ 1.0×A (±10–15%) or ~1.618×A (±15%)
    """
    if len(sw) < 4:
        return None

    # Look at last 4 swings (A end, B end, C end -> 3 legs = 4 points)
    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]  # P0 P1 P2 P3
        types = win["type"].tolist()
        prices = win["price"].tolist()
        idxs = win["idx"].tolist()

        # Must be alternating H/L/H/L or L/H/L/H
        if types not in (["H","L","H","L"], ["L","H","L","H"]):
            continue

        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)  # direction of A
        if dir_A == "side":
            continue

        # B retrace of A
        rB = _retracement_ratio(p0, p1, p2)
        if rB is None:
            continue
        if not (0.30 <= rB <= 0.70):  # a bit flexible around 38.2–61.8
            continue

        # C in same direction as A
        if _dir(p2, p3) != dir_A:
            continue

        # C length relation to A
        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        ratio_CA = _ratio(C_len, A_len) or 0.0

        close_to_1 = 0.85 <= ratio_CA <= 1.15
        close_to_1_618 = 1.35 <= ratio_CA <= 1.85
        if not (close_to_1 or close_to_1_618):
            continue

        direction = "down" if dir_A == "down" else "up"
        completed = True
        current_stage = "zigzag_C_complete"
        next_stage = "resume_trend_up" if direction == "down" else "resume_trend_down"

        # Targets post zigzag: look for retrace of whole A→C
        total = abs(p3 - p0)
        if direction == "up":
            # Zigzag up (rare as correction), next often down
            t382 = p3 - total * 0.382
            t500 = p3 - total * 0.5
            targets = {
                "post_zigzag_retrace_38.2%": float(t382),
                "post_zigzag_retrace_50%": float(t500),
            }
        else:
            # Zigzag down (typical correction), next often up
            t382 = p3 + total * 0.382
            t500 = p3 + total * 0.5
            targets = {
                "post_zigzag_retrace_38.2%": float(t382),
                "post_zigzag_retrace_50%": float(t500),
            }

        return DetectResult(
            pattern="ZIGZAG",
            completed=completed,
            current_stage=current_stage,
            next_stage=next_stage,
            direction=direction,
            targets=targets,
            meta={"window_indices": idxs, "window_types": types, "window_prices": prices, "B_retrace": rB, "C_A_ratio": ratio_CA},
        )
    return None


def _detect_flat(sw: pd.DataFrame) -> Optional[DetectResult]:
    """
    Flat: A-B-C with 3-3-5 spirit (heuristic)
      - B retraces deep ~90–105% of A
      - C ≈ length of A (±15%) or ~1.618×A (±15%) for Expanded
    """
    if len(sw) < 4:
        return None

    for end in range(len(sw), 3, -1):
        win = sw.iloc[end - 4 : end]
        types = win["type"].tolist()
        prices = win["price"].tolist()
        idxs = win["idx"].tolist()
        if types not in (["H","L","H","L"], ["L","H","L","H"]):
            continue

        p0, p1, p2, p3 = prices
        dir_A = _dir(p0, p1)
        if dir_A == "side":
            continue

        rB = _retracement_ratio(p0, p1, p2)
        if rB is None or not (0.90 <= rB <= 1.08):  # ~90–105%
            continue

        # C same direction as A
        if _dir(p2, p3) != dir_A:
            continue

        A_len = _leg_len(p0, p1)
        C_len = _leg_len(p2, p3)
        ratio_CA = _ratio(C_len, A_len) or 0.0

        is_regular = 0.85 <= ratio_CA <= 1.15
        is_expanded = 1.35 <= ratio_CA <= 1.85

        if not (is_regular or is_expanded):
            continue

        direction = "down" if dir_A == "down" else "up"
        completed = True
        current_stage = "flat_C_complete"
        next_stage = "resume_trend_up" if direction == "down" else "resume_trend_down"

        # Post-flat targets: mild retrace of the whole structure
        total = abs(p3 - p0)
        if direction == "down":
            t382 = p3 + total * 0.382
            t500 = p3 + total * 0.5
        else:
            t382 = p3 - total * 0.382
            t500 = p3 - total * 0.5
        targets = {
            "post_flat_retrace_38.2%": float(t382),
            "post_flat_retrace_50%": float(t500),
        }

        return DetectResult(
            pattern="FLAT",
            completed=completed,
            current_stage=current_stage,
            next_stage=next_stage,
            direction=direction,
            targets=targets,
            meta={
                "window_indices": idxs,
                "window_types": types,
                "window_prices": prices,
                "B_retrace": rB,
                "C_A_ratio": ratio_CA,
                "variant": "Expanded" if is_expanded else "Regular",
            },
        )
    return None


def _detect_triangle(sw: pd.DataFrame) -> Optional[DetectResult]:
    """
    Triangle: 5-leg contracting/expanding (A-B-C-D-E). Heuristic checks:
      - 5 alternating swings ending with E
      - Contracting: highs lower, lows higher; Expanding: highs higher, lows lower.
    """
    if len(sw) < 5:
        return None

    for end in range(len(sw), 4, -1):
        win = sw.iloc[end - 5 : end]  # A B C D E
        types = win["type"].tolist()
        prices = win["price"].tolist()
        idxs = win["idx"].tolist()

        if types not in (["H","L","H","L","H"], ["L","H","L","H","L"]):
            continue

        highs = [p for t, p in zip(types, prices) if t == "H"]
        lows  = [p for t, p in zip(types, prices) if t == "L"]

        if len(highs) < 2 or len(lows) < 2:
            continue

        contracting = (all(x > y for x, y in zip(highs, highs[1:])) and
                       all(x < y for x, y in zip(lows,  lows[1:])))
        expanding   = (all(x < y for x, y in zip(highs, highs[1:])) and
                       all(x > y for x, y in zip(lows,  lows[1:])))

        if not (contracting or expanding):
            continue

        # Direction after triangle = thrust in prior trend; we guess using first two legs
        direction = _dir(prices[0], prices[1])
        if direction == "side":
            direction = "up" if contracting else "down"

        completed = True
        current_stage = "triangle_E_complete"
        next_stage = "thrust_" + ("up" if direction == "up" else "down")

        # Thrust target approx width of widest section projected from breakout (E->)
        width = max(highs[0] - lows[0], highs[-1] - lows[-1])
        pE = prices[-1]
        if direction == "up":
            targets = {"triangle_thrust": float(pE + width)}
        else:
            targets = {"triangle_thrust": float(pE - width)}

        return DetectResult(
            pattern="TRIANGLE",
            completed=completed,
            current_stage=current_stage,
            next_stage=next_stage,
            direction=direction,
            targets=targets,
            meta={"window_indices": idxs, "window_types": types, "window_prices": prices,
                  "mode": "Contracting" if contracting else "Expanding", "width": width},
        )
    return None


# =============================================================================
# Extra detectors
# =============================================================================

def _detect_diagonal(sw: pd.DataFrame) -> Optional[DetectResult]:
    """Heuristic diagonal detector (very lightweight; fallback when impulse fails)."""
    if len(sw) < 6:
        return None
    win = sw.iloc[-6:]
    types = win["type"].tolist()
    prices = win["price"].tolist()
    idxs = win["idx"].tolist()
    if types not in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
        return None
    return DetectResult(
        pattern="DIAGONAL",
        completed=True,
        current_stage="wave5_diag",
        next_stage="corrective_A",
        direction="up" if types[-1] == "H" else "down",
        targets={},
        meta={"window_indices": idxs, "window_types": types, "window_prices": prices},
    )


def _detect_double_three(sw: pd.DataFrame) -> Optional[DetectResult]:
    """Simple placeholder for W-X-Y correction (Double Three)."""
    return DetectResult(
        pattern="DOUBLE_THREE",
        completed=False,
        current_stage="WXY_partial",
        next_stage="continue",
        direction="side",
        targets={},
        meta={},
    )


def _detect_triple_three(sw: pd.DataFrame) -> Optional[DetectResult]:
    """Simple placeholder for W-X-Y-X-Z correction (Triple Three)."""
    return DetectResult(
        pattern="TRIPLE_THREE",
        completed=False,
        current_stage="WXYXZ_partial",
        next_stage="continue",
        direction="side",
        targets={},
        meta={},
    )


# =============================================================================
# Public API
# =============================================================================

def analyze_elliott(
    df: pd.DataFrame,
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
    allow_diagonal: bool = True,
    max_swings: int = 30,
) -> Dict[str, object]:
    """
    Basic Elliott analysis from OHLCV DataFrame.
    Requirements: columns ['timestamp','open','high','low','close','volume'] (timestamp optional for swings).
    Returns:
      {pattern, completed, current, next, targets, debug}
    """
    # Minimal data
    needed = {"high", "low", "close"}
    if not needed.issubset(df.columns):
        return _unknown("missing_columns", details={"columns": list(df.columns)})

    # Swings
    sw = _build_swings(df, left=pivot_left, right=pivot_right)
    if len(sw) == 0:
        return _unknown("no_swings")

    if len(sw) > max_swings:
        sw = sw.tail(max_swings).reset_index(drop=True)

    # Try patterns (priority: Impulse/Diagonal -> Zigzag -> Flat -> Triangle -> Extras)
    det = _detect_impulse(sw, allow_diagonal=allow_diagonal)
    if det is not None:
        return _pack(det, sw)

    det = _detect_zigzag(sw)
    if det is not None:
        return _pack(det, sw)

    det = _detect_flat(sw)
    if det is not None:
        return _pack(det, sw)

    det = _detect_triangle(sw)
    if det is not None:
        return _pack(det, sw)

    # Fallback diagonals (very lenient) if strict impulse didn’t claim it
    det = _detect_diagonal(sw)
    if det is not None:
        return _pack(det, sw)

    # Placeholders for composite corrections (optional classification hints)
    det = _detect_double_three(sw)
    if det is not None:
        return _pack(det, sw)

    det = _detect_triple_three(sw)
    if det is not None:
        return _pack(det, sw)

    # Fallback UNKNOWN with direction hint from last two closes
    direction = _dir(float(df["close"].iloc[-5]), float(df["close"].iloc[-1])) if len(df) >= 5 else "side"
    return {
        "pattern": "UNKNOWN",
        "completed": False,
        "current": {"stage": "undetermined", "direction": direction},
        "next": {"stage": "await_more_data", "direction": "side"},
        "targets": {},
        "debug": {"swings": sw.tail(12).to_dict("records"), "reason": "no_pattern_fit"},
    }


# =============================================================================
# Helpers
# =============================================================================

def _unknown(reason: str, details: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    return {
        "pattern": "UNKNOWN",
        "completed": False,
        "current": {"stage": "undetermined", "direction": "side"},
        "next": {"stage": "await_more_data", "direction": "side"},
        "targets": {},
        "debug": {"reason": reason, **(details or {})},
    }


def _pack(det: DetectResult, sw: pd.DataFrame) -> Dict[str, object]:
    return {
        "pattern": det.pattern,
        "completed": det.completed,
        "current": {"stage": det.current_stage, "direction": det.direction},
        "next": {"stage": det.next_stage, "direction": det.direction},
        "targets": det.targets,
        "debug": {
            "swings": sw.tail(12).to_dict("records"),
            **det.meta,
        },
    }
