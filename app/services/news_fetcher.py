from __future__ import annotations
import time
from typing import List, Dict
import feedparser
from app.services.news_sources import RSS_SOURCES

def _parse_entry(src_name: str, e) -> Dict:
    title = getattr(e, "title", "").strip()
    link = getattr(e, "link", "").strip()
    published = ""
    if hasattr(e, "published_parsed") and e.published_parsed:
        published = time.strftime("%Y-%m-%d %H:%M:%S", e.published_parsed)
    elif hasattr(e, "updated_parsed") and e.updated_parsed:
        published = time.strftime("%Y-%m-%d %H:%M:%S", e.updated_parsed)
    return {"source": src_name, "title": title, "link": link, "published": published}

def fetch_rss_many(limit_per_source: int = 5) -> List[Dict]:
    items: List[Dict] = []
    seen = set()
    for src_name, url in RSS_SOURCES:
        feed = feedparser.parse(url)
        for e in (feed.entries or [])[:limit_per_source]:
            it = _parse_entry(src_name, e)
            if not it["title"] or it["title"] in seen:
                continue
            seen.add(it["title"])
            items.append(it)
    items.sort(key=lambda x: x.get("published",""), reverse=True)
    return items

def format_headlines_th(items: List[Dict], max_items: int = 5) -> str:
    lines = ["📣 อัปเดตข่าวล่าสุด"]
    for i, it in enumerate(items[:max_items], 1):
        lines.append(f"{i}. [{it['source']}] {it['title']} — {it['link']}")
    return "\n".join(lines)
