# app/services/notifier_line.py
from __future__ import annotations
import os
from typing import Optional
from linebot import LineBotApi
from linebot.models import TextSendMessage

class LineNotifier:
    """Wrapper สำหรับส่งข้อความเข้า LINE"""

    def __init__(self, access_token: Optional[str] = None, default_to: Optional[str] = None):
        token = access_token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not set")

        self._api = LineBotApi(token)
        self._default_to = (
            default_to
            or os.environ.get("LINE_DEFAULT_TO")
            or os.environ.get("LINE_TO_ID")
        )

    def push_text(self, text: str, to: Optional[str] = None) -> str:
        """ส่งข้อความไปยัง userId/groupId"""
        to_id = to or self._default_to
        if not to_id:
            raise RuntimeError("LINE_DEFAULT_TO / LINE_TO_ID not set and no 'to' provided")

        self._api.push_message(to_id, TextSendMessage(text=text))
        return to_id
