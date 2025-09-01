from __future__ import annotations
import time
from typing import Dict, Tuple

# key -> (expire_at)
_cache: Dict[str, float] = {}

def _now() -> float:
    return time.time()

def seen(key: str, ttl_sec: int = 120) -> bool:
    """Return True ถ้า key นี้พึ่งถูกใช้ในช่วงเวลา ttl_sec (กันซ้ำ)"""
    now = _now()
    # เก็บกวาดค่าเก่าบางส่วน (cheap cleanup)
    if _cache and len(_cache) % 32 == 0:
        expired = [k for k, exp in _cache.items() if exp < now]
        for k in expired:
            _cache.pop(k, None)

    exp = _cache.get(key)
    if exp and exp > now:
        return True
    _cache[key] = now + ttl_sec
    return False
