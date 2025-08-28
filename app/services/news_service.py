from __future__ import annotations
from typing import List, Dict, Iterable, Optional
import re

from app.services.news_fetcher import fetch_rss_many
from app.services.translator import smart_translate_to_thai

def _match_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    t = (text or "").lower()
    for kw in keywords:
        k = kw.strip().lower()
        if not k:
            continue
        if k in t:
            return True
        # ลองแบบคำขึ้นต้น/ลงท้าย (กันคำเว้นวรรค)
        if re.search(rf"\b{re.escape(k)}\b", t):
            return True
    return False

def fetch_latest_news(limit_per_source: int = 3) -> List[Dict]:
    """
    ดึงข่าวล่าสุดจากหลายแหล่งผ่าน RSS (ไม่พึ่งพา paid API)
    คืนค่าเป็น list ของ dict: {source, title, link, published}
    """
    return fetch_rss_many(limit_per_source=limit_per_source)

def build_news_message(
    max_items: int = 6,
    limit_per_source: int = 3,
    keywords: Optional[List[str]] = None,
    translate: bool = True,
) -> str:
    """
    สร้างข้อความสรุปข่าว:
      - คัดกรองด้วยคีย์เวิร์ด (ถ้ากำหนด)
      - แปลหัวข้อเป็นไทยอัตโนมัติ (ถ้า translate=True)
    """
    items = fetch_latest_news(limit_per_source=limit_per_source)

    # กรองด้วยคำค้น (ถ้ามี)
    filtered: List[Dict]
    if keywords:
        filtered = [it for it in items if _match_any_keyword(it.get("title",""), keywords)]
        # ถ้ากรองแล้วว่าง ให้ fallback เป็น items เดิม (กันส่งข้อความว่าง)
        if not filtered:
            filtered = items
    else:
        filtered = items

    # จัดรูปข้อความ
    lines = ["📣 อัปเดตข่าวล่าสุด"]
    for i, it in enumerate(filtered[:max_items], 1):
        title = it.get("title", "")
        if translate:
            try:
                title = smart_translate_to_thai(title)
            except Exception:
                # ถ้าแปลพัง ให้ใช้ต้นฉบับ
                pass
        src = it.get("source", "")
        link = it.get("link", "")
        lines.append(f"{i}. [{src}] {title} — {link}")
    return "\n".join(lines)
