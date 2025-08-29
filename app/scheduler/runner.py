# app/scheduler/runner.py
# =============================================================================
# Scheduler Runner (Multi-Symbol)
# ทำหน้าที่:
# - ตรวจราคาหลายเหรียญ (TopN อัตโนมัติจาก Binance; ดีฟอลต์ TOP_N=50)
# - ประเมิน threshold / cooldown / hysteresis
# - ถ้าถึงเกณฑ์ → ส่งแจ้งเตือนเข้า LINE (broadcast)
# =============================================================================

from __future__ import annotations
import os
import asyncio
import logging
import inspect
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

# ใช้ provider ใหม่ (sync) แล้วหุ้มด้วย asyncio.to_thread
from app.adapters.price_provider import get_price

# ===== LINE Delivery =====
from app.adapters.delivery_line import broadcast_message

# ===== ccxt (อาจไม่มีในบางสภาพแวดล้อม) =====
try:
    import ccxt  # ใช้ดึง Top-N จาก Binance แบบไม่ต้อง auth
except Exception:
    ccxt = None  # fallback จะใช้ลิสต์คงที่

# ===== Default static fallbacks (ถ้าโหลด Top-N ไม่ได้) =====
FALLBACK_TOP = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "TON", "TRX"]


# ==============================
# Helpers
# ==============================
def _normalize_symbol_to_usdt(symbol: str) -> str:
    """
    แปลงสัญลักษณ์ให้เป็นคู่กับ USDT โดยอัตโนมัติ ถ้าใส่แค่ 'BTC' → 'BTCUSDT'
    ถ้าเป็นรูปแบบที่ใช้อยู่แล้ว เช่น 'BTCUSDT' หรือ 'BTC/USDT' จะคืนค่าเดิม
    หมายเหตุ: ถ้าเป็นสเตเบิลเองอย่าง 'USDT' ให้ยกเว้น (ไม่แจ้งเตือน)
    """
    s = (symbol or "").strip().upper()
    if "/" in s or s.endswith("USDT"):
        return s
    if s in {"USDT", "USDC"}:
        # ไม่เหมาะกับการ alert เปอร์เซ็นต์ราคา ต่อให้ provider รับได้ เราขอข้ามไป
        raise RuntimeError(f"skip stable symbol: {s}")
    return f"{s}USDT"


def _load_top_symbols(n: int = 50) -> List[str]:
    """
    ดึง Top-N ตาม 24h quote volume ของคู่ *USDT บน Binance
    - คืนค่าเป็น list ของ base symbols (เช่น ["BTC","ETH",...])
    - ตัด stablecoins ออก (USDT/USDC/FDUSD/TUSD/BUSD/DAI)
    - ถ้า ccxt ไม่มี/ล้มเหลว → ใช้ FALLBACK_TOP
    """
    STABLES = {"USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI"}
    if ccxt is None:
        logger.warning("ccxt not available; using FALLBACK_TOP")
        return FALLBACK_TOP
    try:
        ex = ccxt.binance({"enableRateLimit": True})
        tickers = ex.fetch_tickers()  # {"BTC/USDT": {...}, ...}
        rows = []
        for sym, tk in tickers.items():
            if not sym.endswith("/USDT"):
                continue
            base, quote = sym.split("/")
            if base in STABLES or quote in STABLES:
                continue
            qv = tk.get("quoteVolume")
            if qv is None:
                info = tk.get("info", {})
                try:
                    qv = float(info.get("quoteVolume") or 0.0)
                except Exception:
                    qv = 0.0
            try:
                qv = float(qv)
            except Exception:
                qv = 0.0
            rows.append((base, qv))
        rows.sort(key=lambda x: x[1], reverse=True)
        out, seen = [], set()
        limit = int(os.getenv("TOP_N", n))
        for base, _ in rows:
            if base in seen:
                continue
            seen.add(base)
            out.append(base)
            if len(out) >= limit:
                break
        if not out:
            logger.warning("no symbols loaded from ccxt; using FALLBACK_TOP")
        return out or FALLBACK_TOP
    except Exception as e:
        logger.exception("load top symbols failed: %s", e)
        return FALLBACK_TOP


async def _aget_numeric_price(symbol_like: str) -> float:
    """
    ดึงราคาปัจจุบันโดย:
    - แปลง symbol ให้เป็นคู่ USDT ถ้าจำเป็น
    - เรียก get_price (sync) ผ่าน asyncio.to_thread เพื่อไม่บล็อก event loop
    """
    pair = _normalize_symbol_to_usdt(symbol_like)
    px = await asyncio.to_thread(get_price, pair)
    if px is None:
        raise RuntimeError(f"price not available for {pair}")
    return float(px)


def _format_alert_text(symbol: str, current_price: float, pct_change: float) -> str:
    """สร้างข้อความแจ้งเตือนสำหรับส่ง LINE (อิง USDT)"""
    direction = "↑" if pct_change >= 0 else "↓"
    return f"[ALERT] {symbol} {direction}{abs(pct_change):.2f}% | Price: {current_price:,.2f} USDT"


def _is_alert_enabled() -> bool:
    """
    รองรับทั้งกรณีที่ AlertSettings มีหรือไม่มีฟิลด์ enabled:
    - ถ้ามี: ใช้ค่าจาก settings
    - ถ้าไม่มี: อ่าน ENV ALERT_ENABLED (ค่าเริ่มต้น = 1 → เปิด)
    """
    enabled_attr = getattr(alert_settings, "enabled", None)
    if enabled_attr is not None:
        try:
            return bool(enabled_attr) if isinstance(enabled_attr, bool) else bool(int(enabled_attr))
        except Exception:
            return True
    try:
        return bool(int(os.getenv("ALERT_ENABLED", "1")))
    except Exception:
        return True


def _get_threshold_pct() -> float:
    # หน่วยเป็น "เปอร์เซ็นต์" (เช่น 3 = 3%)
    # ดีฟอลต์ 3 แทน 0.03 เพื่อสอดคล้องกับ pct ที่คำนวณ *100 ไว้แล้ว
    return float(
        getattr(alert_settings, "threshold_pct",
                getattr(alert_settings, "THRESHOLD_PCT", 3))
    )


def _get_cooldown_sec() -> int:
    return int(
        getattr(alert_settings, "cooldown_sec",
                getattr(alert_settings, "COOLDOWN_SEC", 600))
    )


def _get_poll_seconds() -> int:
    # ถ้ามี poll_sec ใช้เลย; ไม่มีก็แปลงจาก PRICE_ALERT_INTERVAL_MIN → วินาที
    v = getattr(alert_settings, "poll_sec", None)
    if v is not None:
        return int(v)
    mins = int(getattr(alert_settings, "PRICE_ALERT_INTERVAL_MIN", 5))
    return max(1, mins * 60)


async def _maybe_await_send(text: str) -> None:
    """
    เรียกส่งข้อความ LINE โดยรองรับทั้งฟังก์ชัน sync/async:
    - ถ้า broadcast_message คืน awaitable → await
    - ถ้าเป็น sync → เรียกตรง ๆ
    """
    ret = broadcast_message(text)
    if inspect.isawaitable(ret):
        await ret


# ==============================
# Tick รอบเดียว (หลายเหรียญ)
# ==============================
async def tick_once(symbols: Optional[List[str]] = None, dry_run: bool = False) -> None:
    if not _is_alert_enabled():
        logger.info("Alerts disabled; skip tick.")
        return

    if symbols is None:
        symbols = _load_top_symbols(n=int(os.getenv("TOP_N", "50")))

    threshold = _get_threshold_pct()
    cooldown = _get_cooldown_sec()

    for symbol in symbols:
        try:
            # ดึงราคา (จะ auto-normalize เป็น *USDT)
            current_price = await _aget_numeric_price(symbol)
            state = get_state(symbol)
            baseline = state.get("baseline")

            # รอบแรก → ตั้ง baseline
            if baseline is None:
                set_baseline(symbol, current_price)
                logger.info("Baseline set for %s at %.6f", symbol, current_price)
                continue

            # คำนวณ % การเปลี่ยนแปลง (เป็นหน่วยเปอร์เซ็นต์)
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
                    await _maybe_await_send(text)

                mark_alerted(symbol)
                set_baseline(symbol, current_price)
                logger.info("Alert fired; baseline reset for %s at %.6f", symbol, current_price)

        except Exception as e:
            logger.exception("Error in tick for %s: %s", symbol, e)


# ==============================
# Scheduler loop (หลายเหรียญ)
# ==============================
async def run_scheduler(symbols: Optional[List[str]] = None) -> None:
    poll = _get_poll_seconds()
    if symbols is None:
        symbols = _load_top_symbols(n=int(os.getenv("TOP_N", "50")))

    logger.info(
        "Scheduler started: poll every %ds (symbols=%d loaded, threshold=%.2f%%, cooldown=%ds)",
        poll, len(symbols), _get_threshold_pct(), _get_cooldown_sec(),
    )

    while True:
        try:
            await tick_once(symbols=symbols, dry_run=False)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled; shutting down.")
            break
        except Exception as e:
            logger.exception("Scheduler encountered an error: %s", e)
            # ล้มรอบนี้ แต่ยังคงวนรอบถัดไป
        await asyncio.sleep(poll)
