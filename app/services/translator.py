# app/services/translator.py
from __future__ import annotations

import os
import re
import time
import json
import html
import hmac
import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List

import requests  # ใช้เฉพาะกรณีเรียก API ภายนอก (ถ้าไม่ตั้งค่า จะไม่ถูกเรียก)

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
class TranslationRequest:
    text: str
    target_lang: str = "th"   # เช่น "th", "en", "ja"
    source_lang: str = "auto" # "auto" ให้ provider ตรวจจับอัตโนมัติ
    formality: Optional[str] = None  # "default" | "more" | "less" (ขึ้นกับ provider)

@dataclass
class TranslationResult:
    text: str
    detected_source_lang: Optional[str] = None
    provider: str = "fallback"
    cached: bool = False


# =============================================================================
# PROVIDER LAYER (Plug-in)
# =============================================================================
class BaseTranslator(ABC):
    """Interface ของผู้ให้บริการแปล"""
    name: str = "base"

    @abstractmethod
    def translate(self, req: TranslationRequest) -> TranslationResult:
        raise NotImplementedError


class FallbackTranslator(BaseTranslator):
    """
    ตัวสำรอง: ถ้าระบุ provider ไม่ครบ/ใช้ API ไม่ได้
    - ถ้าข้อความเป็นไทยอยู่แล้ว → คืนเดิม
    - ถ้า target=th แต่ข้อความเป็นอังกฤษสั้น ๆ → ใช้ mini-dict แปลคำง่าย ๆ (กัน UI ว่าง)
    - ที่เหลือ: passthrough (คืนเดิม)
    """
    name = "fallback"

    _mini_dict_en2th: Dict[str, str] = {
        "bitcoin": "บิตคอยน์",
        "crypto": "คริปโต",
        "price": "ราคา",
        "rise": "เพิ่มขึ้น",
        "fall": "ลดลง",
        "fed": "เฟด",
        "interest rate": "อัตราดอกเบี้ย",
        "inflation": "เงินเฟ้อ",
        "sec": "ก.ล.ต. สหรัฐฯ",
        "approve": "อนุมัติ",
        "reject": "ปฏิเสธ",
        "etf": "กองทุนอีทีเอฟ",
    }

    def _looks_thai(self, s: str) -> bool:
        return bool(re.search(r"[\u0E00-\u0E7F]", s))

    def translate(self, req: TranslationRequest) -> TranslationResult:
        text = req.text or ""
        if not text.strip():
            return TranslationResult(text="", detected_source_lang=None, provider=self.name)

        if self._looks_thai(text):
            # เดิมเป็นไทยแล้ว
            return TranslationResult(text=text, detected_source_lang="th", provider=self.name)

        if req.target_lang.lower() == "th":
            # mini translate แบบง่ายมาก (เฉพาะคำยอดฮิต)
            t = text
            for en, th in sorted(self._mini_dict_en2th.items(), key=lambda x: -len(x[0])):
                t = re.sub(rf"\b{re.escape(en)}\b", th, t, flags=re.IGNORECASE)
            return TranslationResult(text=t, detected_source_lang="en", provider=self.name)

        # ไม่รองรับกรณีอื่น → passthrough
        return TranslationResult(text=text, detected_source_lang=None, provider=self.name)


class GoogleTranslateAPI(BaseTranslator):
    """
    Google Cloud Translation API v2/v3 (ต้องตั้งค่า API key หรือ Service)
    โหมดง่าย: ใช้ v2 REST ด้วย API Key: GOOGLE_TRANSLATE_API_KEY
    Docs: https://cloud.google.com/translate/docs/reference/rest
    """
    name = "google"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.getenv("GOOGLE_TRANSLATE_API_KEY", "").strip()
        self.timeout = timeout

    def translate(self, req: TranslationRequest) -> TranslationResult:
        if not self.api_key:
            raise RuntimeError("GOOGLE_TRANSLATE_API_KEY not set")

        url = "https://translation.googleapis.com/language/translate/v2"
        params = {
            "q": req.text,
            "target": req.target_lang,
        }
        if req.source_lang and req.source_lang != "auto":
            params["source"] = req.source_lang

        try:
            r = requests.post(f"{url}?key={self.api_key}", data=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            tr = data["data"]["translations"][0]
            text = html.unescape(tr.get("translatedText", ""))  # Google จะ escape HTML entity
            detected = tr.get("detectedSourceLanguage")
            return TranslationResult(text=text, detected_source_lang=detected, provider=self.name)
        except Exception as e:
            logger.warning(f"[GoogleTranslateAPI] error: {e}")
            # ให้ service ตัดสินใจ fallback ต่อ
            raise


class DeepLAPI(BaseTranslator):
    """
    DeepL API (Free/Pro) ผ่าน key: DEEPL_API_KEY
    Docs: https://www.deepl.com/docs-api
    """
    name = "deepl"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.getenv("DEEPL_API_KEY", "").strip()
        self.timeout = timeout
        # ฟรี: api-free.deepl.com / โปร: api.deepl.com
        self.endpoint = os.getenv("DEEPL_ENDPOINT", "https://api-free.deepl.com/v2/translate")

    def translate(self, req: TranslationRequest) -> TranslationResult:
        if not self.api_key:
            raise RuntimeError("DEEPL_API_KEY not set")

        data = {
            "text": req.text,
            "target_lang": req.target_lang.upper(),  # DeepL ต้องเป็น EN/DE/TH (บาง account อาจยังไม่รองรับ TH)
        }
        if req.source_lang and req.source_lang != "auto":
            data["source_lang"] = req.source_lang.upper()
        if req.formality:
            data["formality"] = req.formality  # default | more | less

        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}

        try:
            r = requests.post(self.endpoint, data=data, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            js = r.json()
            translations = js.get("translations", [])
            if not translations:
                raise RuntimeError("Empty translation result")
            tt = translations[0]
            return TranslationResult(
                text=tt.get("text", ""),
                detected_source_lang=tt.get("detected_source_language"),
                provider=self.name,
            )
        except Exception as e:
            logger.warning(f"[DeepLAPI] error: {e}")
            raise


class OpenAITranslator(BaseTranslator):
    """
    ตัวเลือกเสริม: ใช้ OpenAI API แปลข้อความ (เช่น gpt-4o-mini)
    ENV:
      OPENAI_API_KEY
      OPENAI_TRANSLATE_MODEL (เช่น "gpt-4o-mini-transcribe" หรือ "gpt-4o-mini")
    หมายเหตุ: โค้ดนี้เป็น generic JSON REST; ปรับ endpoint ตามเวอร์ชันจริงที่ใช้
    """
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 20):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        self.endpoint = os.getenv("OPENAI_CHAT_COMPLETIONS_ENDPOINT", "https://api.openai.com/v1/chat/completions")

    def translate(self, req: TranslationRequest) -> TranslationResult:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        system = (
            "You are a professional translator. Preserve original meaning, keep numbers, tickers, and URLs unchanged. "
            "Output plain text only, without quotes."
        )
        prompt = f"Translate to {req.target_lang} (source={req.source_lang}):\n{req.text}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            r = requests.post(self.endpoint, headers=headers, data=json.dumps(body), timeout=self.timeout)
            r.raise_for_status()
            js = r.json()
            msg = js["choices"][0]["message"]["content"]
            return TranslationResult(text=msg.strip(), detected_source_lang=None, provider=self.name)
        except Exception as e:
            logger.warning(f"[OpenAITranslator] error: {e}")
            raise


# =============================================================================
# SERVICE LAYER
# =============================================================================
class TranslatorService:
    """
    ตัวจัดการเลือก provider + cache + rate-limit + fallback
    ENV ที่รองรับ:
      TRANSLATOR_PROVIDER="google|deepl|openai|fallback" (default: fallback)
      TRANSLATOR_CACHE_TTL=600   (วินาที)
      TRANSLATOR_RATE_LIMIT_QPS=2  (คำขอต่อวินาที)
      GOOGLE_TRANSLATE_API_KEY=...
      DEEPL_API_KEY=...
      OPENAI_API_KEY=...
    """
    def __init__(self):
        self.provider_name = (os.getenv("TRANSLATOR_PROVIDER", "fallback") or "fallback").lower().strip()
        self.cache_ttl = int(os.getenv("TRANSLATOR_CACHE_TTL", "600"))
        self.qps = float(os.getenv("TRANSLATOR_RATE_LIMIT_QPS", "2"))
        self._last_ts: float = 0.0

        # cache: key=(provider, source, target, formality, hash(text)) -> (ts, TranslationResult)
        self._cache: Dict[str, Tuple[float, TranslationResult]] = {}

        # สร้าง provider ที่ใช้งาน
        self.provider = self._build_provider(self.provider_name)

        # fallback เสมอ (กันล่ม)
        self._fallback = FallbackTranslator()

        logger.info(f"[TranslatorService] provider={self.provider_name}, cache_ttl={self.cache_ttl}, qps={self.qps}")

    # ---------- Public API ----------
    def translate(self, text: str, target_lang: str = "th", source_lang: str = "auto",
                  formality: Optional[str] = None, use_cache: bool = True) -> TranslationResult:
        req = TranslationRequest(text=text, target_lang=target_lang, source_lang=source_lang, formality=formality)

        # 1) Cache hit?
        cache_key = self._cache_key(self.provider_name, req)
        if use_cache:
            hit = self._cache_get(cache_key)
            if hit:
                return TranslationResult(
                    text=hit.text,
                    detected_source_lang=hit.detected_source_lang,
                    provider=hit.provider,
                    cached=True,
                )

        # 2) Rate limit
        self._respect_qps()

        # 3) Try main provider
        try:
            result = self.provider.translate(req)
        except Exception as e:
            logger.warning(f"[TranslatorService] main provider failed ({self.provider_name}): {e}")
            # 4) Fallback
            result = self._fallback.translate(req)

        # 5) Save cache
        if use_cache:
            self._cache_set(cache_key, result)

        return result

    # ---------- Internal ----------
    def _build_provider(self, name: str) -> BaseTranslator:
        if name == "google":
            return GoogleTranslateAPI()
        if name == "deepl":
            return DeepLAPI()
        if name == "openai":
            return OpenAITranslator()
        return FallbackTranslator()

    def _cache_key(self, provider: string, req: TranslationRequest) -> str:  # type: ignore[name-defined]
        # hash ข้อความเพื่อประหยัดหน่วยความจำ
        digest = hashlib.sha1(req.text.encode("utf-8")).hexdigest()
        return f"{provider}::{req.source_lang}::{req.target_lang}::{req.formality or '-'}::{digest}"

    def _cache_get(self, key: str) -> Optional[TranslationResult]:
        item = self._cache.get(key)
        if not item:
            return None
        ts, result = item
        if (time.time() - ts) > self.cache_ttl:
            # หมดอายุ
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return result

    def _cache_set(self, key: str, result: TranslationResult) -> None:
        self._cache[key] = (time.time(), result)

    def _respect_qps(self) -> None:
        if self.qps <= 0:
            return
        min_interval = 1.0 / self.qps
        now = time.time()
        diff = now - self._last_ts
        if diff < min_interval:
            time.sleep(min_interval - diff)
        self._last_ts = time.time()


# =============================================================================
# CONVENIENCE
# =============================================================================
_service_singleton: Optional[TranslatorService] = None

def get_service() -> TranslatorService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = TranslatorService()
    return _service_singleton


# =============================================================================
# HELPERS / UTILITIES
# =============================================================================
def is_probably_thai(s: str) -> bool:
    return bool(re.search(r"[\u0E00-\u0E7F]", s))

def smart_translate_to_thai(text: str) -> str:
    """
    ฟังก์ชันสั้น ๆ ที่ใช้บ่อย: แปลเป็นไทยด้วย service ปัจจุบัน
    - ข้อความที่เป็นไทยอยู่แล้ว → คืนเดิม
    - อื่น ๆ → เรียก service ตาม provider
    """
    if is_probably_thai(text):
        return text
    svc = get_service()
    res = svc.translate(text, target_lang="th", source_lang="auto")
    return res.text


# =============================================================================
# MAIN (manual test)
# =============================================================================
if __name__ == "__main__":
    os.environ.setdefault("TRANSLATOR_PROVIDER", "fallback")  # เปลี่ยนเป็น google|deepl|openai เมื่อพร้อม
    svc = get_service()

    samples = [
        "Bitcoin price jumps after Fed hints at rate cuts.",
        "SEC delays decision on spot Ethereum ETF.",
        "เฟดประกาศคงดอกเบี้ยตามคาด",
    ]
    for s in samples:
        out = svc.translate(s, target_lang="th")
        logger.info(f"[{out.provider} cached={out.cached}] {s} -> {out.text}")
