# app/scheduler/runner.py
# =============================================================================
# Scheduler Runner (Multi-Symbol)
# ทำหน้าที่: รันงาน background → ตรวจราคาหลายเหรียญ (BTC, ETH, ETC...)
# ประเมิน threshold/cooldown/hysteresis → ถ้าถึงเกณฑ์ → ส่งแจ้งเตือนเข้า LINE (broadcast)
# =============================================================================

import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ===== Settings =====
from app.settings.alerts import alert_settings

# ===== State / Utils =====
from app.utils.state_store import (
    get_state,
    set_baseline,
    should_alert,
    mark_alerted,
)
from app.features.alerts.percentage_change import evaluate_percentage_alert

# ===== Providers =====
try:
    from app.adapters.price_provider import get_price as provider_get_price  # async
except Exception:
    provider_get_price = None

try:
    from app.utils.crypto_price import get_price as crypto_get_price  # sync fallback
except Exception:
    crypto_get_price = None

# ===== LINE Delivery =====
from app.adapters.delivery_line import broadcast_message

# ===== Symbols Config =====
try:
    from app.config.symbols import SUPPORTED as SUPPORTED_SYMBOLS
except Exception:
    SUPPORTED_SYMBOLS = [alert_settings.symbol.upper()]


# ==============================
# Helper: ดึงราคาปัจจุบันเป็น float
# ==============================
async def _aget_numeric_price(symbol: str) -> float:
    """พยายามดึงราคาจาก provider (async) → fallback (sync)"""
    if provider_get_price is not None:
        price = await provider_get_price(symbol)
        if price is None:
            raise RuntimeError(f"price_provider.get_price({symbol}) returned None")
        return float(price)
    if crypto_get_price is not None:
        price = crypto_get_price(symbol)
        if price is None:
            raise RuntimeError(f"crypto_price.get_price({symbol}) returned None")
        return float(price)
    raise RuntimeError("No numeric price source available.")


def _format_alert_text(symbol: str, current_price: float, pct_change: float) -> str:
    """สร้างข้อความแจ้งเตือนสำหรับส่ง LINE"""
    direction = "↑" if pct_change >= 0 else "↓"
    return f"[ALERT] {symbol} {direction}{abs(pct_change):.2f}% | Price: {current_price:,.2f} USD"


# ==============================
# Tick รอบเดียว (หลายเหรียญ)
# ==============================
async def tick_once(symbols: Optional[List[str]] = None, dry_run: bool = False) -> None:
    if not alert_settings.enabled:
        logger.debug("Alert is disabled; skip tick.")
        return

    if symbols is None:
        symbols = SUPPORTED_SYMBOLS

    threshold = float(alert_settings.threshold_pct)
    cooldown = int(alert_settings.cooldown_sec)
    hysteresis = float(alert_settings.hysteresis_pct)

    for symbol in symbols:
        try:
            # ดึงราคา
            current_price = await _aget_numeric_price(symbol)
            state = get_state(symbol)
            baseline = state.get("baseline")
            last_state = state.get("last_state", "idle")

            # รอบแรก → ตั้ง baseline
            if baseline is None:
                set_baseline(symbol, current_price)
                logger.info("Baseline set for %s at %.6f; waiting for next tick.", symbol, current_price)
                continue

            # Evaluate hysteresis
            result = evaluate_percentage_alert(
                current_price=current_price,
                baseline_price=baseline,
                threshold_pct=threshold,
                hysteresis_pct=hysteresis,
                last_state=last_state,
            )
            pct = float(result["pct_change"])
            crossed = bool(result["crossed"])
            ready_by_hysteresis = bool(result["ready_to_alert"])
            new_state = str(result["new_state"])

            # Cooldown
            ready_by_cooldown = should_alert(
                symbol,
                pct_change=pct,
                threshold_pct=threshold,
                cooldown_sec=cooldown,
            )
            ready_to_fire = ready_by_hysteresis and ready_by_cooldown

            logger.info(
                "TICK %s: price=%.6f baseline=%.6f pct=%+.3f%% crossed=%s hysteresis_ok=%s cooldown_ok=%s new_state=%s",
                symbol, current_price, baseline, pct, crossed, ready_by_hysteresis, ready_by_cooldown, new_state,
            )

            state["last_state"] = new_state

            if ready_to_fire:
                text = _format_alert_text(symbol, current_price, pct)
                if dry_run:
                    logger.info("[DRY-RUN] Would send LINE: %s", text)
                else:
                    await broadcast_message(text)

                mark_alerted(symbol)
                set_baseline(symbol, current_price)
                logger.info("Alert fired; baseline reset for %s at %.6f", symbol, current_price)

        except Exception as e:
            logger.exception("Error in tick for %s: %s", symbol, e)


# ==============================
# Scheduler loop (หลายเหรียญ)
# ==============================
async def run_scheduler(symbols: Optional[List[str]] = None) -> None:
    poll = int(alert_settings.poll_sec)
    if symbols is None:
        symbols = SUPPORTED_SYMBOLS

    logger.info(
        "Scheduler started: poll every %ds (symbols=%s, threshold=%.2f%%, cooldown=%ds, hysteresis=%.2f%%)",
        poll, symbols, alert_settings.threshold_pct, alert_settings.cooldown_sec, alert_settings.hysteresis_pct,
    )
    try:
        while True:
            await tick_once(symbols=symbols, dry_run=False)
            await asyncio.sleep(poll)
    except asyncio.CancelledError:
        logger.info("Scheduler cancelled; shutting down.")
    except Exception as e:
        logger.exception("Scheduler encountered an error: %s", e)
        await asyncio.sleep(poll)
