# jobs/push_news.py
from __future__ import annotations

import os
import io
import re
import json
import time
import pathlib
import logging
from dataclasses import asdict
from typing import List, Optional, Iterable, Dict, Tuple

# --- Logging -----------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    h = logging.StreamHandler()
    f = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    h.setFormatter(f)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# --- Services (News + Translator) --------------------------------------------
from app.services.news_service import get_service as get_news_service, NewsItem  # type: ignore
from app.services.translator import get_service as get_translator_service, is_probably_thai  # type: ignore

# --- LINE notifier (ยืดหยุ่นชื่อไฟล์) -----------------------------------------
# จะพยายามใช้ services/notifier_line.py ก่อน → ถ้าไม่มีค่อย fallback ไป adapters/delivery_line.py
class _LineNotifier:
    def __init__(self):
        self._impl = None
        self._mode = "unknown"

        # 1) services/notifier_line.py (แนะนำ)
        try:
            from app.services.notifier_line import LineNotifier as LN  # type: ignore
            self._impl = LN()
            self._mode = "services.notifier_line.LineNotifier"
            logger.info("[LineNotifier] using services.notifier_line.LineNotifier")
            return
        except Exception as e:
            logger.info(f"[LineNotifier] services.notifier_line not available: {e}")

        # 2) adapters/delivery_line.py (ต้องมีเมธอด broadcast_text / push_text)
        try:
            from app.adapters.delivery_line import broadcast_text, push_text  # type: ignore

            class _Wrap:
                def broadcast(self, text: str):
                    return broadcast_text(text)
                def push(self, user_id: str, text: str):
                    return push_text(user_id, text)

            self._impl = _Wrap()
            self._mode = "adapters.delivery_line"
            logger.info("[LineNotifier] using adapters.delivery_line")
            return
        except Exception as e:
            logger.warning(f"[LineNotifier] adapters.delivery_line not available: {e}")

        # 3) fail-safe: dummy (log only)
        class _Dummy:
            def broadcast(self, text: str):
                logger.warning(f"[LineNotifier.Dummy] broadcast: {text[:200]}...")
            def push(self, user_id: str, text: str):
                logger.warning(f"[LineNotifier.Dummy] push to {user_id}: {text[:200]}...")

        self._impl = _Dummy()
        self._mode = "dummy"
        logger.warning("[LineNotifier] using Dummy notifier (no real send)")

    def broadcast(self, text: str):
        return self._impl.broadcast(text)

    def push(self, user_id: str, text: str):
        return self._impl.push(user_id, text)


# =============================================================================
# CONFIG LAYER
# =============================================================================
class NewsPushConfig:
    """
    ตั้งค่าผ่าน ENV:
      NEWS_PUSH_ENABLED=true|false
      NEWS_PUSH_LIMIT=3             # จำนวนข่าวต่อรอบ
      NEWS_PUSH_KEYWORDS="btc,bitcoin,crypto,ethereum,sec,fed,interest rate"
      NEWS_PUSH_BROADCAST=true      # true=ส่ง broadcast, false=push เฉพาะ USER_IDS
      NEWS_PUSH_USER_IDS="Uxxxx,Uyzzz"  # ใช้เมื่อ BROADCAST=false
      NEWS_TRANSLATE_TO_TH=true     # แปลไทย
      NEWS_TITLE_MAX=120            # ตัดความยาว title
      NEWS_SUMMARY_MAX=260          # ตัดความยาวสรุป
      NEWS_APPEND_SOURCE=true       # แสดง [source]
      NEWS_APPEND_TIME=true         # แสดงเวลา (UTC)
      NEWS_NEWLINE_BETWEEN_ITEMS=2  # เว้นบรรทัดระหว่างข่าว
      NEWS_SENT_DB="out/news_sent_ids.json"  # กันส่งซ้ำ
    """
    def __init__(self):
        self.enabled = (os.getenv("NEWS_PUSH_ENABLED", "true").lower() in ("1", "true", "yes"))
        self.limit = int(os.getenv("NEWS_PUSH_LIMIT", "3"))

        _kw = os.getenv("NEWS_PUSH_KEYWORDS", "btc,bitcoin,crypto,ethereum,sec,fed,interest rate")
        self.keywords = [k.strip().lower() for k in _kw.split(",") if k.strip()]

        self.broadcast = (os.getenv("NEWS_PUSH_BROADCAST", "true").lower() in ("1", "true", "yes"))
        _users = os.getenv("NEWS_PUSH_USER_IDS", "").strip()
        self.user_ids = [u.strip() for u in _users.split(",") if u.strip()]

        self.translate_to_th = (os.getenv("NEWS_TRANSLATE_TO_TH", "true").lower() in ("1", "true", "yes"))

        self.title_max = int(os.getenv("NEWS_TITLE_MAX", "120"))
        self.summary_max = int(os.getenv("NEWS_SUMMARY_MAX", "260"))

        self.append_source = (os.getenv("NEWS_APPEND_SOURCE", "true").lower() in ("1", "true", "yes"))
        self.append_time = (os.getenv("NEWS_APPEND_TIME", "true").lower() in ("1", "true", "yes"))
        self.nl_items = int(os.getenv("NEWS_NEWLINE_BETWEEN_ITEMS", "2"))

        self.sent_db = os.getenv("NEWS_SENT_DB", "out/news_sent_ids.json")

    def __repr__(self) -> str:
        return f"<NewsPushConfig enabled={self.enabled} limit={self.limit} broadcast={self.broadcast} users={len(self.user_ids)}>"


# =============================================================================
# STORE LAYER (กันส่งซ้ำ)
# =============================================================================
class SentStore:
    """
    เก็บ ID ข่าวที่เคยส่งแล้ว → ป้องกันส่งซ้ำ
    ใช้ไฟล์ JSON: {"ids": ["sha1..", "sha1.."], "ts": 1690000000}
    """
    def __init__(self, path: str):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = {"ids": [], "ts": int(time.time())}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
                if "ids" not in self._data:
                    self._data["ids"] = []
            except Exception as e:
                logger.warning(f"[SentStore] load error, recreate: {e}")
                self._data = {"ids": [], "ts": int(time.time())}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def seen(self, nid: str) -> bool:
        return nid in self._data["ids"]

    def mark(self, nid: str):
        if nid not in self._data["ids"]:
            self._data["ids"].append(nid)
            # จำกัดขนาดเล็กน้อย (กันไฟล์โต)
            if len(self._data["ids"]) > 5000:
                self._data["ids"] = self._data["ids"][-3000:]
            self._data["ts"] = int(time.time())
            self._save()


# =============================================================================
# FORMATTERS (ข้อความที่จะส่งเข้า LINE)
# =============================================================================
def _truncate(s: Optional[str], max_len: int) -> str:
    if not s:
        return ""
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 1)].rstrip() + "…"

def _format_one(item: NewsItem, cfg: NewsPushConfig, th_text: Optional[str]) -> str:
    """คืน string ของข่าวหนึ่งรายการ"""
    title = _truncate(item.title or "(no title)", cfg.title_max)
    summary_src = th_text if (th_text and cfg.translate_to_th) else (item.summary or item.content or "")
    summary = _truncate(summary_src, cfg.summary_max)

    bullets: List[str] = []
    bullets.append(f"📰 {title}")
    if summary:
        bullets.append(f"• {summary}")

    meta: List[str] = []
    if cfg.append_source and item.source:
        meta.append(f"[{item.source}]")
    if cfg.append_time and item.published_at:
        meta.append(f"{item.published_at} UTC")
    meta_line = " ".join(meta).strip()
    if meta_line:
        bullets.append(meta_line)

    if item.url:
        bullets.append(f"🔗 {item.url}")

    return "\n".join(bullets)

def _join_items(blocks: List[str], nl: int) -> str:
    sep = "\n" * nl
    header = "📣 อัปเดตข่าวสำคัญล่าสุด\n"
    return header + sep + sep.join(blocks)


# =============================================================================
# JOB LAYER
# =============================================================================
def run_push_news(dry_run: bool = False) -> Tuple[int, int]:
    """
    ดึงข่าว → แปลไทย (ออปชัน) → กันซ้ำ → ส่งเข้า LINE
    Return: (num_picked, num_sent)
    """
    cfg = NewsPushConfig()
    logger.info(f"[run_push_news] start with {cfg}")

    if not cfg.enabled:
        logger.info("[run_push_news] disabled by NEWS_PUSH_ENABLED")
        return (0, 0)

    # 1) ดึงข่าว
    news = get_news_service()
    items = news.get_latest(limit=cfg.limit * 3)  # ดึงมาเผื่อคัดทิ้ง
    logger.info(f"[run_push_news] fetched={len(items)}")

    # 2) กรองด้วย keywords (ถ้าตั้งค่าไว้)
    if cfg.keywords:
        items = _filter_by_keywords(items, cfg.keywords)
        logger.info(f"[run_push_news] after keyword filter={len(items)}")

    # 3) กันซ้ำ
    store = SentStore(cfg.sent_db)
    fresh: List[NewsItem] = []
    for it in items:
        if not store.seen(it.id):
            fresh.append(it)
        if len(fresh) >= cfg.limit:
            break
    logger.info(f"[run_push_news] fresh_to_send={len(fresh)}")

    if not fresh:
        logger.info("[run_push_news] nothing new to send")
        return (0, 0)

    # 4) แปลไทย (ถ้าต้องการ)
    blocks: List[str] = []
    translator = get_translator_service() if cfg.translate_to_th else None

    for it in fresh:
        translated_summary: Optional[str] = None
        if cfg.translate_to_th:
            base_text = it.summary or it.content or it.title or ""
            if base_text and not is_probably_thai(base_text):
                try:
                    tr = translator.translate(base_text, target_lang="th", source_lang="auto")  # type: ignore
                    translated_summary = tr.text
                except Exception as e:
                    logger.warning(f"[run_push_news] translate fail: {e}")
                    translated_summary = None
            else:
                translated_summary = base_text

        blocks.append(_format_one(it, cfg, translated_summary))

    # 5) Compose message
    msg = _join_items(blocks, cfg.nl_items)
    logger.info(f"[run_push_news] message length={len(msg)}")

    # 6) ส่งเข้า LINE
    notifier = _LineNotifier()
    sent = 0

    if dry_run:
        logger.info("[run_push_news] DRY RUN (no send). Preview:\n" + msg)
    else:
        try:
            if cfg.broadcast:
                notifier.broadcast(msg)
                sent = len(fresh)
            else:
                # push ทีละ user
                for uid in cfg.user_ids:
                    notifier.push(uid, msg)
                sent = len(fresh) * max(1, len(cfg.user_ids))
        except Exception as e:
            logger.error(f"[run_push_news] send error: {e}")
            sent = 0

    # 7) Mark sent
    if sent > 0:
        for it in fresh:
            store.mark(it.id)

    return (len(fresh), sent)


# =============================================================================
# HELPERS
# =============================================================================
def _filter_by_keywords(items: List[NewsItem], keywords: List[str]) -> List[NewsItem]:
    if not keywords:
        return items
    ks = [k.lower() for k in keywords]
    out: List[NewsItem] = []
    for it in items:
        blob = f"{it.title or ''} {it.summary or ''} {it.content or ''}".lower()
        if any(k in blob for k in ks):
            out.append(it)
    return out


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Push latest news to LINE")
    parser.add_argument("--dry-run", action="store_true", help="ไม่ส่งจริง แค่พิมพ์ตัวอย่างข้อความ")
    args = parser.parse_args()

    picked, sent = run_push_news(dry_run=args.dry_run)
    logger.info(f"[push_news] picked={picked}, sent={sent}")
