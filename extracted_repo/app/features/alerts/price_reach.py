from __future__ import annotations
import asyncio, time
from typing import Dict, Tuple, Callable, Optional

_WATCHES: Dict[Tuple[str, str], Tuple[float, float, float]] = {}
_RUNNING = False

def add_watch(user_id: str, symbol: str, entry: float, tol: float = 0.0) -> None:
    _WATCHES[(user_id, symbol.upper())] = (float(entry), float(tol), time.time())

def remove_watch(user_id: str, symbol: str) -> bool:
    return _WATCHES.pop((user_id, symbol.upper()), None) is not None

async def run_loop(get_price: Callable[[str], float | None],
                   on_hit: Callable[[str, str, float, float], None],
                   *, interval_sec: int = 15) -> None:
    global _RUNNING
    if _RUNNING: return
    _RUNNING = True
    try:
        while True:
            for (uid, sym), (entry, tol, _) in list(_WATCHES.items()):
                try:
                    px = await _maybe_async(get_price, sym)
                except Exception:
                    px = None
                if px is None: 
                    continue
                hit = abs(px - entry) <= tol if tol > 0 else (px == entry)
                if hit:
                    try: on_hit(uid, sym, float(px), float(entry))
                    except Exception: pass
                    _WATCHES.pop((uid, sym), None)
            await asyncio.sleep(interval_sec)
    finally:
        _RUNNING = False

async def _maybe_async(f, *a, **k):
    import inspect
    return (await f(*a, **k)) if inspect.iscoroutinefunction(f) else f(*a, **k)
