# tests/test_keyword_reply.py
import pytest
from app.features.replies.keyword_reply import get_reply, parse_price_command

def test_get_reply_keywords():
    assert get_reply("สวัสดี") is not None
    assert get_reply("btc") == "BTC นี่มันคาสิโนชัด ๆ 🎰"
    assert get_reply("ไม่รู้จัก") is None

def test_parse_price_command_basic():
    assert parse_price_command("ราคา BTC") == "BTCUSDT"
    assert parse_price_command("price eth") == "ETHUSDT"
    assert parse_price_command("ราคา BTCUSDT") == "BTCUSDT"

def test_parse_price_command_invalid():
    assert parse_price_command("hello world") is None
    assert parse_price_command("") is None
