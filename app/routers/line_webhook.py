import os
import json
import hmac
import base64
import hashlib
import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Request, Header, Response

# 🔹 keyword reply + parse price
from app.features.replies.keyword_reply import get_reply, parse_price_command
# 🔹 wave analysis service
from app.services.wave_service import analyze_wave, build_brief_message
# 🔹 price resolver
from app.utils.crypto_price import resolver
# 🔹 mock analysis tools
import numpy as np, pandas as pd
from app.analysis.scenarios import analyze_scenarios

router = APIRouter(tags=["line"])

# ENV config
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

logger = logging.getLogger(__name__)


def _verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """ตรวจสอบ X-Line-Signature"""
    try:
        mac = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None, convert_underscores=False),
) -> Response:
    raw: bytes = await request.body()
    try:
        payload: Dict[str, Any] = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.error("LINE webhook: invalid JSON body")
        return Response(status_code=400)

    # verify signature
    if CHANNEL_SECRET and x_line_signature:
        ok = _verify_signature(CHANNEL_SECRET, raw, x_line_signature)
        if not ok:
            logger.warning("LINE webhook: signature verification FAILED")
            return Response(status_code=403)

    for ev in payload.get("events", []):
        try:
            if ev.get("type") == "message" and "replyToken" in ev:
                text = ev.get("message", {}).get("text", "").strip()
                reply_token = ev["replyToken"]

                reply_text = None

                # --- Integration: analyze SYMBOL TF ---
                if text.lower().startswith("analyze"):
                    parts = text.split()
                    if len(parts) >= 3:
                        symbol = parts[1].upper()
                        tf = parts[2].upper()
                        try:
                            payload = analyze_wave(symbol, tf)
                            reply_text = build_brief_message(payload)
                        except Exception as e:
                            logger.exception("Analyze failed")
                            reply_text = f"❌ วิเคราะห์ไม่สำเร็จ: {e}"
                    else:
                        reply_text = "ใช้รูปแบบ: analyze SYMBOL TF\nเช่น: analyze BTCUSDT 1D"

                # --- ราคา <symbol> ---
                if not reply_text:
                    symbol = parse_price_command(text)
                    if symbol:
                        try:
                            price = None
                            if hasattr(resolver, "price") and callable(getattr(resolver, "price")):
                                maybe = resolver.price(symbol)
                                price = (await maybe) if hasattr(maybe, "__await__") else maybe
                            elif hasattr(resolver, "get") and callable(getattr(resolver, "get")):
                                price = resolver.get(symbol)
                            elif hasattr(resolver, "resolve") and callable(getattr(resolver, "resolve")):
                                price = resolver.resolve(symbol)
                        except Exception as e:
                            logger.warning("resolver error: %s", e)
                            price = None

                        if price is not None:
                            reply_text = f"📈 {symbol}\nราคา: {float(price):,.2f}"
                        else:
                            reply_text = f"ขอโทษครับ ดึงราคา {symbol} ไม่ได้"

                # --- MOCK วิเคราะห์ ---
                if not reply_text and text.lower().strip() in {"mock", "วิเคราะห์ mock"}:
                    try:
                        np.random.seed(0)
                        close = np.cumsum(np.random.randn(150)) + 50000
                        high  = close + np.abs(np.random.randn(150)) * 50
                        low   = close - np.abs(np.random.randn(150)) * 50
                        open_ = close + np.random.randn(150)
                        vol   = np.random.randint(100, 1000, size=150)

                        df = pd.DataFrame({
                            "open": open_, "high": high, "low": low, "close": close, "volume": vol
                        })
                        payload = analyze_scenarios(df, symbol="BTCUSDT", tf="1D")
                        pct = payload.get("percent", {})
                        lv  = payload.get("levels", {})
                        reply_text = (
                            "🧪 MOCK ANALYSIS (BTCUSDT 1D)\n"
                            f"↑ {pct.get('up',0)}%  ↓ {pct.get('down',0)}%  ↔ {pct.get('side',0)}%\n"
                            f"RH: {lv.get('recent_high', None):,.2f} | RL: {lv.get('recent_low', None):,.2f}\n"
                            f"EMA50: {lv.get('ema50', None):,.2f}"
                        )
                    except Exception as e:
                        logger.exception("mock analysis failed")
                        reply_text = f"❌ วิเคราะห์ mock ไม่สำเร็จ: {e}"

                # --- Otherwise: keyword reply
                if not reply_text:
                    reply_text = get_reply(text) or "ไม่เข้าใจคำสั่งครับ"

                await _reply_text(reply_token, reply_text)

        except Exception as e:
            logger.warning("Reply failed (non-blocking): %s", e)

    return Response(status_code=200)


async def _reply_text(reply_token: str, text: str) -> None:
    """เรียก LINE reply API (ข้ามเมื่อเป็น token ทดสอบ/ไม่มี ACCESS TOKEN)"""
    # ข้ามเมื่อยังไม่ตั้ง token หรือเป็น token จำลอง
    if not CHANNEL_ACCESS_TOKEN or reply_token in {"DUMMY", "TEST_REPLY_TOKEN"} or reply_token.startswith("DUMMY"):
        logging.warning("Skip reply (test mode). token=%s text=%s", reply_token, text)
        return

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code == 400 and "Invalid reply token" in r.text:
            logging.warning("Skip reply (invalid/expired token).")
            return
        if r.status_code != 200:
            logging.warning("Reply API failed %s: %s", r.status_code, r.text)
        else:
            logging.info("Reply OK")

    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code != 200:
            logging.warning("Reply API failed %s: %s", r.status_code, r.text)
        else:
            logging.info("Reply OK")
