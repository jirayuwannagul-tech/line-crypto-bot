"""
app.analysis package

- ทำให้ import แบบ `from app.analysis import elliott` ใช้งานได้
- หลีกเลี่ยงวงจร import (ไม่ import อะไรจาก app.logic ที่นี่)
- ใช้ lazy import เพื่อไม่โหลดโมดูลย่อยโดยไม่จำเป็น
"""

from typing import TYPE_CHECKING
import importlib

__all__ = [
    "elliott",
    "fibonacci",
    "indicators",
    "filters",
    "dow",
    "timeframes",
]

def __getattr__(name: str):
    if name in __all__:
        mod = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = mod  # cache
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

if TYPE_CHECKING:
    # เพื่อให้ type checker มองเห็นสัญลักษณ์ย่อยได้ (ไม่รันจริงตอน runtime)
    from . import elliott, fibonacci, indicators, filters, dow, timeframes  # noqa: F401
