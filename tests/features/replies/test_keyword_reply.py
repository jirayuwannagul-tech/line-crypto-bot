# tests/test_keyword_reply.py
import pytest
from app.features.replies.keyword_reply import get_reply, parse_price_command

def test_get_reply_keywords():
    # กรณีทักทาย
    assert get_reply("สวัสดี") is not None

    # btc ไม่ให้ชนกับชั้นราคา → keyword layer ต้องไม่ตอบ
    assert get_reply("btc") is None

    # ข้อความไม่รู้จัก → ต้อง None
    assert get_reply("ไม่รู้จัก") is None

def test_parse_price_command_basic():
    # ตรวจจับคำสั่งราคาแบบต่าง ๆ
    assert parse_price_command("ราคา BTC") == "BTCUSDT"
    assert parse_price_command("price eth") == "ETHUSDT"
    assert parse_price_command("ราคา BTCUSDT") == "BTCUSDT"

def test_parse_price_command_invalid():
    # ข้อความที่ไม่ใช่คำสั่งราคา → None
    assert parse_price_command("hello world") is None
    assert parse_price_command("") is None
