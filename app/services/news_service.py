from __future__ import annotations
from typing import List, Dict

# ใช้ตัวดึงข่าวผ่าน RSS
from app.services.news_fetcher import fetch_rss_many, format_headlines_th

def fetch_latest_news(limit_per_source: int = 3) -> List[Dict]:
    """
    ดึงข่าวล่าสุดจากหลายแหล่งผ่าน RSS (ไม่พึ่งพา paid API)
    คืนค่าเป็น list ของ dict: {source, title, link, published}
    """
    return fetch_rss_many(limit_per_source=limit_per_source)

def build_news_message(max_items: int = 6, limit_per_source: int = 3) -> str:
    """
    สร้างข้อความสรุปข่าวภาษาไทย พร้อมลิงก์ แสดงหัวข้อไม่เกิน max_items
    ใช้กับ LINE broadcast ได้ทันที
    """
    items = fetch_latest_news(limit_per_source=limit_per_source)
    return format_headlines_th(items, max_items=max_items)
