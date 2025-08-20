# =============================================================================
# Scheduler Runner (Multi-Symbol)
# ทำหน้าที่:
# - รันงาน background → ตรวจราคาหลายเหรียญ (Top 10)
# - ประเมิน threshold / cooldown / hysteresis
# - ถ้าถึงเกณฑ์ → ส่งแจ้งเตือนเข้า LINE (broadcast)
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
from app.utils.crypto_price import get_price_usd

# ===== LINE Delivery =====
from app.adapters.delivery_line import broadcast_message


# ===== Top 10 เหรียญที่ติดตามอัตโนมัติ =====
TOP10_SYMBOLS = ["BTC","ETH","USDT","BNB","SOL","XRP","USDC","DOGE","ADA","AVAX"]


# ==============================
# Helper: ดึงราคาปัจจุบันเป็น float
# ==============================
async def _aget_numeric_price(symbol: str) -> float:
    price = await get_price_usd(symbol)
    if price is None:
        raise RuntimeError(f"price not available for {symbol}")
    return float(price)


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
        symbols = TOP10_SYMBOLS

    threshold = float(alert_settings.threshold_pct)
    cooldown = int(alert_settings.cooldown_sec)

    for symbol in symbols:
        try:
            # ดึงราคา
            current_price = await _aget_numeric_price(symbol)
            state = get_state(symbol)
            baseline = state.get("baseline")

            # รอบแรก → ตั้ง baseline
            if baseline is None:
                set_baseline(symbol, current_price)
                logger.info("Baseline set for %s at %.6f", symbol, current_price)
                continue

            # คำนวณ % การเปลี่ยนแปลง
            pct = ((current_price - baseline) / baseline) * 100

            ready_by_cooldown = should_alert(
                symbol,
                pct_change=pct,
                threshold_pct=threshold,
                cooldown_sec=cooldown,
            )

            logger.info(
                "TICK %s: price=%.6f baseline=%.6f pct=%+.3f%% cooldown_ok=%s",
                symbol, current_price, baseline, pct, ready_by_cooldown,
            )

            if ready_by_cooldown:
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
        symbols = TOP10_SYMBOLS

    logger.info(
        "Scheduler started: poll every %ds (symbols=%s, threshold=%.2f%%, cooldown=%ds)",
        poll, symbols, alert_settings.threshold_pct, alert_settings.cooldown_sec,
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
