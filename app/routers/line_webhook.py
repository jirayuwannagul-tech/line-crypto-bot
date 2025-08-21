# app/routers/line_webhook.py
import os
import json
import hmac
import base64
import hashlib
import logging
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Request, Header, Response

# 🔹 keyword reply + คำสั่งราคา
from app.features.replies.keyword_reply import get_reply, parse_price_command
# 🔹 วิเคราะห์จริง (service เดิมของโปรเจกต์)
from app.services.wave_service import analyze_wave, build_brief_message
# 🔹 ตัวดึงราคา (resolver)
from app.utils.crypto_price import resolver
# 🔹 MOCK วิเคราะห์ (ข้อมูลจำลอง)
import numpy as np
import pandas as pd
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

    # verify signature (ถ้าตั้ง SECRET ไว้)
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

                reply_text: str | List[str] | None = None

                # --- 1) วิเคราะห์จริง: "analyze SYMBOL TF"
                if text.lower().startswith("analyze"):
                    parts = text.split()
                    if len(parts) >= 3:
                        symbol = parts[1].upper()
                        tf = parts[2].upper()
                        try:
                            reply_text = [
                                f"🔔 กำลังวิเคราะห์ {symbol} {tf} ...",
                                build_brief_message(analyze_wave(symbol, tf)),
                            ]
                        except Exception as e:
                            logger.exception("Analyze failed")
                            reply_text = f"❌ วิเคราะห์ไม่สำเร็จ: {e}"
                    else:
                        reply_text = "ใช้รูปแบบ: analyze SYMBOL TF\nเช่น: analyze BTCUSDT 1D"

                # --- 2) คำสั่งราคา: "ราคา BTC" / "price eth"
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
                            reply_text = [
                                f"🔔 รับคำสั่งราคา {symbol}",
                                f"📈 {symbol}\nราคา: {float(price):,.2f}",
                            ]
                        else:
                            reply_text = f"ขอโทษครับ ดึงราคา {symbol} ไม่ได้"

                # --- 3) วิเคราะห์ MOCK: "mock" หรือ "วิเคราะห์ mock"
                if not reply_text and text.lower().strip() in {"mock", "วิเคราะห์ mock"}:
                    try:
                        np.random.seed(0)
                        close = np.cumsum(np.random.randn(150)) + 50000
                        high = close + np.abs(np.random.randn(150)) * 50
                        low = close - np.abs(np.random.randn(150)) * 50
                        open_ = close + np.random.randn(150)
                        vol = np.random.randint(100, 1000, size=150)

                        df = pd.DataFrame(
                            {"open": open_, "high": high, "low": low, "close": close, "volume": vol}
                        )
                        payload = analyze_scenarios(df, symbol="BTCUSDT", tf="1D")
                        pct = payload.get("percent", {})
                        lv = payload.get("levels", {})
                        reply_text = [
                            "🔔 กำลังประมวลผล (MOCK) ...",
                            (
                                "🧪 MOCK ANALYSIS (BTCUSDT 1D)\n"
                                f"↑ {pct.get('up',0)}%  ↓ {pct.get('down',0)}%  ↔ {pct.get('side',0)}%\n"
                                f"RH: {lv.get('recent_high', None):,.2f} | RL: {lv.get('recent_low', None):,.2f}\n"
                                f"EMA50: {lv.get('ema50', None):,.2f}"
                            ),
                        ]
                    except Exception as e:
                        logger.exception("mock analysis failed")
                        reply_text = f"❌ วิเคราะห์ mock ไม่สำเร็จ: {e}"

                # --- 4) อย่างอื่น: keyword map ปกติ
                if not reply_text:
                    reply_text = get_reply(text) or "ไม่เข้าใจคำสั่งครับ"

                await _reply_text(reply_token, reply_text)

        except Exception as e:
            logger.warning("Reply failed (non-blocking): %s", e)

    return Response(status_code=200)


async def _reply_text(reply_token: str, text: str | List[str]) -> None:
    """เรียก LINE reply API (รองรับหลายข้อความ และข้ามเมื่อเป็น token ทดสอบ/ไม่มี ACCESS TOKEN)"""
    # ทดสอบในเครื่อง/Render: ใช้ token จำลองจะข้ามการยิงไป LINE
    test_token = str(reply_token) in {"DUMMY", "TEST_REPLY_TOKEN"} or str(reply_token).startswith("DUMMY")
    if (not CHANNEL_ACCESS_TOKEN) or test_token:
        logging.warning("Skip reply (test mode). token=%s text=%s", reply_token, text)
        return

    messages = [{"type": "text", "text": t} for t in (text if isinstance(text, list) else [text])]

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    body = {"replyToken": reply_token, "messages": messages}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code == 400 and "Invalid reply token" in r.text:
            logging.warning("Skip reply (invalid/expired token). token=%s", reply_token)
            return
        if r.status_code != 200:
            logging.warning("Reply API failed %s: %s", r.status_code, r.text)
        else:
            logging.info("Reply OK")

        # === DEBUG: PUSH TEST ENDPOINT ===
@router.post("/push-test")
async def push_test(payload: Dict[str, Any]) -> Response:
    """
    ยิงทดสอบ PUSH โดยไม่ต้องใช้ replyToken

    JSON ตัวอย่าง:
    { "to": "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "text": "🔔 BTC แจ้งเตือนทดสอบ 50,000" }
    หรือหลายบรรทัด:
    { "to": "U...", "text": ["🔔 กำลังเตือน...", "📈 BTC 50,000"] }
    """
    to = str(payload.get("to", "")).strip()
    text = payload.get("text", None)

    # validate input
    if not to or text is None:
        return Response(
            status_code=400,
            content=json.dumps({"error": "missing 'to' or 'text'"}),
            media_type="application/json",
        )

    # ข้ามการยิงจริงเมื่อยังไม่ตั้งค่า Token
    if not CHANNEL_ACCESS_TOKEN:
        logger.warning("CHANNEL_ACCESS_TOKEN not set; skip push.")
        return Response(
            status_code=200,
            content=json.dumps({"ok": True, "skipped": "no CHANNEL_ACCESS_TOKEN"}),
            media_type="application/json",
        )

    # สร้าง message list ให้รองรับทั้ง str และ list[str]
    if isinstance(text, str):
        msgs = [{"type": "text", "text": text}]
    elif isinstance(text, list):
        msgs = [{"type": "text", "text": str(t)} for t in text if t is not None]
        if not msgs:
            return Response(
                status_code=400,
                content=json.dumps({"error": "empty 'text' list"}),
                media_type="application/json",
            )
    else:
        return Response(
            status_code=400,
            content=json.dumps({"error": "'text' must be string or list of strings"}),
            media_type="application/json",
        )

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"to": to, "messages": msgs}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code != 200:
            logger.warning("Push API failed %s: %s", r.status_code, r.text)
            # ส่งสถานะ/ข้อความจาก LINE กลับไปให้ดีบักง่าย
            return Response(status_code=r.status_code, content=r.text, media_type="application/json")
        logger.info("Push OK")
        return Response(status_code=200, content=json.dumps({"ok": True}), media_type="application/json")
    except Exception as e:
        logger.exception("push-test failed: %s", e)
        return Response(
            status_code=500,
            content=json.dumps({"ok": False, "error": str(e)}),
            media_type="application/json",
        )

