# app/services/news_service.py
from __future__ import annotations

import os
import re
import time
import json
import math
import hashlib
import logging
import textwrap
import datetime as dt
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Iterable
from urllib.parse import urlparse
import requests
from xml.etree import ElementTree as ET

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# =============================================================================
# DTO / MODEL LAYER
# =============================================================================
@dataclass
class NewsItem:
    id: str
    source: str
    title: str
    url: str
    published_at: Optional[str]  # ISO string (UTC)
    summary: Optional[str] = None
    content: Optional[str] = None
    tickers: Optional[List[str]] = None
    lang: str = "en"

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# SOURCE LAYER (ดึงข่าวจากแต่ละแหล่ง)
# =============================================================================
class BaseSource:
    """Interface สำหรับแหล่งข่าว"""
    name: str = "base"

    def fetch(self) -> List[NewsItem]:
        raise NotImplementedError


class RssSource(BaseSource):
    """
    ดึงข่าวจาก RSS/Atom โดยไม่พึ่ง library ภายนอก (ใช้ xml.etree)
    รองรับฟีดทั่วไป (title/link/pubDate/summary/content)
    """
    def __init__(self, url: str, name: Optional[str] = None, timeout: int = 10):
        self.url = url
        self.name = name or self._infer_name(url)
        self.timeout = timeout

    def _infer_name(self, url: str) -> str:
        try:
            netloc = urlparse(url).netloc
            return netloc.replace("www.", "")
        except Exception:
            return "rss"

    def fetch(self) -> List[NewsItem]:
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[RssSource] fetch error: {self.url} -> {e}")
            return []

        try:
            root = ET.fromstring(resp.content)
        except Exception as e:
            logger.warning(f"[RssSource] XML parse error: {self.url} -> {e}")
            return []

        # รองรับทั้ง RSS และ Atom
        # RSS: channel/item
        # Atom: feed/entry
        items: List[NewsItem] = []
        if root.tag.lower().endswith("rss") or root.find("channel") is not None:
            channel = root.find("channel")
            if channel is None:
                return []
            for it in channel.findall("item"):
                title = _text(it.find("title"))
                link = _text(it.find("link"))
                pub = _parse_datetime(_text(it.find("pubDate")))
                summary = _strip_html(_text(it.find("description")))
                content = summary
                nid = _make_id(self.name, title or link or str(pub))
                items.append(
                    NewsItem(
                        id=nid,
                        source=self.name,
                        title=title or "(no title)",
                        url=link or "",
                        published_at=pub,
                        summary=summary,
                        content=content,
                        tickers=None,
                        lang="en",
                    )
                )
        else:
            # Atom
            ns = _detect_ns(root.tag)
            for it in root.findall(f"{ns}entry"):
                title = _text(it.find(f"{ns}title"))
                link_el = it.find(f"{ns}link")
                link = (link_el.get("href") if link_el is not None else "") if hasattr(link_el, "get") else ""
                pub = _parse_datetime(_text(it.find(f"{ns}updated")) or _text(it.find(f"{ns}published")))
                summary = _strip_html(_text(it.find(f"{ns}summary")))
                content = _strip_html(_text(it.find(f"{ns}content"))) or summary
                nid = _make_id(self.name, title or link or str(pub))
                items.append(
                    NewsItem(
                        id=nid,
                        source=self.name,
                        title=title or "(no title)",
                        url=link or "",
                        published_at=pub,
                        summary=summary,
                        content=content,
                        tickers=None,
                        lang="en",
                    )
                )
        return items


class NewsApiSource(BaseSource):
    """
    ดึงข่าวจาก NewsAPI (https://newsapi.org)
    ต้องตั้ง env: NEWSAPI_API_KEY
    """
    name = "newsapi"

    def __init__(self,
                 query: str = "bitcoin OR crypto OR ethereum",
                 language: str = "en",
                 page_size: int = 50,
                 timeout: int = 10):
        self.api_key = os.getenv("NEWSAPI_API_KEY", "").strip()
        self.query = query
        self.language = language
        self.page_size = min(max(page_size, 1), 100)
        self.timeout = timeout

    def fetch(self) -> List[NewsItem]:
        if not self.api_key:
            logger.info("[NewsApiSource] NEWSAPI_API_KEY not set, skip.")
            return []

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": self.query,
            "language": self.language,
            "pageSize": self.page_size,
            "sortBy": "publishedAt",
        }
        headers = {"X-Api-Key": self.api_key}

        try:
            r = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning(f"[NewsApiSource] fetch error: {e}")
            return []

        articles = data.get("articles", [])
        items: List[NewsItem] = []
        for a in articles:
            title = a.get("title") or "(no title)"
            link = a.get("url") or ""
            source_name = (a.get("source") or {}).get("name") or "newsapi"
            desc = a.get("description")
            content = a.get("content")
            published = a.get("publishedAt")
            nid = _make_id(source_name, title + link)

            items.append(
                NewsItem(
                    id=nid,
                    source=source_name,
                    title=title,
                    url=link,
                    published_at=published,
                    summary=_strip_html(desc),
                    content=_strip_html(content) if content else None,
                    tickers=None,
                    lang=self.language,
                )
            )
        return items


# =============================================================================
# SERVICE LAYER (รวม, กรอง, ล้างข้อความ, เดดัพ)
# =============================================================================
class NewsService:
    """
    รวมข่าวจากหลาย Source → กรองด้วยคีย์เวิร์ด → เดดัพ → คืนลิสต์ล่าสุด
    - ปรับแต่งผ่าน ENV:
        NEWS_RSS_URLS="https://www.federalreserve.gov/feeds/press_all.xml,https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"
        NEWS_KEYWORDS="bitcoin,btc,crypto,ethereum,sec,fed,interest rate"
        NEWS_MAX_ITEMS=20
        NEWS_TTL_SECONDS=300
        NEWS_INCLUDE_NEWSAPI=true
        NEWSAPI_API_KEY=xxxxx
    """
    def __init__(self):
        # RSS list
        rss_env = os.getenv("NEWS_RSS_URLS", "").strip()
        if rss_env:
            rss_urls = [u.strip() for u in rss_env.split(",") if u.strip()]
        else:
            # ค่าเริ่มต้น (เปลี่ยน/เพิ่มได้)
            rss_urls = [
                "https://www.federalreserve.gov/feeds/press_all.xml",
                "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
                "https://cointelegraph.com/rss",  # อาจช้า/บางครั้งบล็อก แต่ลองไว้ก่อน
                "https://www.reuters.com/markets/cryptocurrency/rss",
            ]

        self.sources: List[BaseSource] = [RssSource(u) for u in rss_urls]

        include_newsapi = os.getenv("NEWS_INCLUDE_NEWSAPI", "false").lower() in ("1", "true", "yes")
        if include_newsapi:
            self.sources.append(NewsApiSource())

        self.keywords = [k.strip().lower() for k in os.getenv("NEWS_KEYWORDS", "bitcoin,btc,crypto,ethereum,sec,fed,interest rate").split(",")]
        self.max_items = int(os.getenv("NEWS_MAX_ITEMS", "20"))
        self.ttl_seconds = int(os.getenv("NEWS_TTL_SECONDS", "300"))

        # cache ภายใน service (ป้องกันยิงซ้ำถี่)
        self._cache_ts: float = 0.0
        self._cache_items: List[NewsItem] = []

    # ---------- Public API ----------
    def get_latest(self, limit: Optional[int] = None) -> List[NewsItem]:
        """ดึงลิสต์ข่าวล่าสุด (เดดัพ/กรองแล้ว), ใช้ cache ตาม TTL"""
        now = time.time()
        if (now - self._cache_ts) < self.ttl_seconds and self._cache_items:
            items = self._cache_items
        else:
            items = self._refresh()
            self._cache_items = items
            self._cache_ts = now

        if limit:
            return items[:limit]
        return items

    def search(self, query: str, limit: int = 10) -> List[NewsItem]:
        """ค้นหาจากแคชปัจจุบัน (กรณีอยากให้ push_news เลือกคำสำคัญเฉพาะกิจ)"""
        q = query.lower().strip()
        items = self.get_latest()
        hits = [x for x in items if q in (x.title or "").lower() or q in (x.summary or "").lower()]
        return hits[:limit]

    # ---------- Internal ----------
    def _refresh(self) -> List[NewsItem]:
        all_items: List[NewsItem] = []
        for src in self.sources:
            try:
                fetched = src.fetch()
                logger.info(f"[NewsService] fetched {len(fetched)} from {getattr(src, 'name', src.__class__.__name__)}")
                all_items.extend(fetched)
            except Exception as e:
                logger.warning(f"[NewsService] source error {src}: {e}")

        cleaned = [self._clean_item(x) for x in all_items]
        deduped = self._dedupe(cleaned)
        filtered = self._apply_keywords(deduped, self.keywords)
        sorted_items = sorted(filtered, key=lambda x: (x.published_at or ""), reverse=True)
        return sorted_items[: self.max_items]

    def _clean_item(self, it: NewsItem) -> NewsItem:
        title = _normalize_whitespace(it.title)
        summary = _normalize_whitespace(it.summary) if it.summary else None
        content = _normalize_whitespace(it.content) if it.content else None
        return NewsItem(
            id=it.id,
            source=it.source,
            title=title,
            url=it.url,
            published_at=_iso_utc(it.published_at),
            summary=summary,
            content=content,
            tickers=it.tickers or _guess_tickers(title, summary),
            lang=it.lang,
        )

    def _dedupe(self, items: List[NewsItem]) -> List[NewsItem]:
        seen: set = set()
        out: List[NewsItem] = []
        for it in items:
            key = hashlib.md5(f"{(it.title or '').lower()}::{(it.url or '').lower()}".encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    def _apply_keywords(self, items: List[NewsItem], keywords: List[str]) -> List[NewsItem]:
        if not keywords:
            return items
        def match(x: NewsItem) -> bool:
            blob = f"{x.title} {x.summary or ''} {x.content or ''}".lower()
            return any(k in blob for k in keywords)
        return [x for x in items if match(x)]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def _text(node: Optional[ET.Element]) -> Optional[str]:
    if node is None:
        return None
    return (node.text or "").strip()

def _strip_html(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    # ตัดแท็กแบบง่าย ๆ
    s = re.sub(r"<[^>]+>", " ", s)
    return _normalize_whitespace(s)

def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _iso_utc(s: Optional[str]) -> Optional[str]:
    """พยายาม normalize เป็น ISO UTC (ไม่เคร่ง; ถ้า parse ไม่ได้ คืนค่าเดิม)"""
    if not s:
        return s
    try:
        # รองรับรูปแบบทั่วไป: RFC822, RFC3339
        try:
            # RFC3339/ISO
            dt_obj = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            # RFC822 ด้วย email.utils
            from email.utils import parsedate_to_datetime
            dt_obj = parsedate_to_datetime(s)
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
        return dt_obj.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return s

def _make_id(source: str, seed: str) -> str:
    return hashlib.sha1(f"{source}::{seed}".encode()).hexdigest()

def _detect_ns(tag: str) -> str:
    # คืนค่า namespace prefix ของ Atom ถ้ามี
    if tag.startswith("{"):
        ns = tag.split("}")[0].strip("{")
        return f"{{{ns}}}"
    return ""

def _parse_datetime(s: Optional[str]) -> Optional[str]:
    return _iso_utc(s)

def _guess_tickers(title: Optional[str], summary: Optional[str]) -> List[str]:
    blob = f"{title or ''} {summary or ''}".upper()
    hits = []
    for sym in ("BTC", "ETH", "SOL", "BNB", "DOGE"):
        if re.search(rf"\b{sym}\b", blob):
            hits.append(sym)
    return hits


# =============================================================================
# CONVENIENCE (ใช้ใน job / script อื่น)
# =============================================================================
def get_service() -> NewsService:
    """สำหรับ import ไปใช้ใน jobs/push_news.py"""
    return NewsService()


if __name__ == "__main__":
    # Quick manual test
    svc = get_service()
    items = svc.get_latest(limit=10)
    for i, it in enumerate(items, 1):
        logger.info(f"{i:02d}. [{it.source}] {it.title} | {it.published_at} | {it.url}")
