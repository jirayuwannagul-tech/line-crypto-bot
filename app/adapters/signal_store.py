# [ไฟล์] app/adapters/signal_store.py  (แทนที่ทั้งไฟล์)

# =============================================================================
# LAYER: CONFIG & IMPORTS
# =============================================================================
from __future__ import annotations
from typing import Optional, Dict, Any, Tuple
import os
import json
import sqlite3
import time
from pathlib import Path
import datetime

# optional deps for safe JSON encoding
try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

DEFAULT_DB_PATH = os.getenv("SIGNAL_DB_PATH", "app/data/signals.db")
Path("app/data").mkdir(parents=True, exist_ok=True)


# =============================================================================
# LAYER: DB SCHEMA
# =============================================================================
SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  tf TEXT NOT NULL,
  signal_key TEXT NOT NULL,   -- ใช้กันซ้ำ (เช่น f"{symbol}:{tf}:{entry:.2f}:{sl:.2f}:{tp3:.2f}")
  status TEXT NOT NULL,       -- OPEN | CLOSED
  entry REAL,
  sl REAL,
  tp1 REAL,
  tp2 REAL,
  tp3 REAL,
  opened_at INTEGER NOT NULL, -- epoch seconds
  closed_at INTEGER,          -- epoch seconds
  outcome TEXT,               -- TP1|TP2|TP3|SL|MANUAL|CANCEL
  last_text TEXT,             -- ข้อความที่ส่งไป LINE ล่าสุด
  payload_json TEXT           -- payload เต็ม (สำหรับอ้างอิง/สถิติ)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_signal_unique_open
ON signals(symbol, tf, signal_key, status);

-- บล็อคการส่งสัญญาณใหม่จนกว่าจะได้ TP1
CREATE TABLE IF NOT EXISTS blocks (
  symbol TEXT NOT NULL,
  tf TEXT NOT NULL,
  blocked INTEGER NOT NULL DEFAULT 0,  -- 0 = ปลดบล็อค, 1 = บล็อค
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, tf)
);
"""


# =============================================================================
# LAYER: JSON ENCODER (รองรับ Timestamp / numpy / datetime)
# =============================================================================
def _json_default(o):
    # pandas.Timestamp → ISO8601
    if pd is not None and isinstance(o, getattr(pd, "Timestamp", ())):
        return o.isoformat()
    # datetime → ISO8601
    if isinstance(o, datetime.datetime):
        return o.astimezone(datetime.timezone.utc).isoformat() if o.tzinfo else o.isoformat()
    # numpy scalar → python scalar
    if np is not None and isinstance(o, (np.integer,)):
        return int(o)
    if np is not None and isinstance(o, (np.floating,)):
        return float(o)
    if np is not None and isinstance(o, (np.bool_,)):
        return bool(o)
    # set/tuple → list
    if isinstance(o, (set, tuple)):
        return list(o)
    # fallback เป็น str
    return str(o)

def dumps_safe(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


# =============================================================================
# LAYER: DB CORE (connection helpers)
# =============================================================================
def _conn(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with _conn(db_path) as c:
        c.executescript(SCHEMA)


# =============================================================================
# LAYER: SIGNAL DOMAIN — Identity / CRUD / UPSERT
# =============================================================================
def build_signal_key(symbol: str, tf: str, entry: float, sl: float, tp3: float) -> str:
    """กุญแจเอกลักษณ์ของสัญญาณ เพื่อกันยิงซ้ำในสถานะ OPEN"""
    return f"{symbol.upper()}:{tf.upper()}:{round(entry,2)}:{round(sl,2)}:{round(tp3,2)}"

def get_open_signal(symbol: str, tf: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """ดึงสัญญาณ OPEN ล่าสุดของ symbol/tf (ถ้ามี)"""
    q = """SELECT id, symbol, tf, signal_key, status, entry, sl, tp1, tp2, tp3, opened_at, last_text, payload_json
           FROM signals WHERE symbol=? AND tf=? AND status='OPEN' ORDER BY id DESC LIMIT 1"""
    with _conn(db_path) as c:
        row = c.execute(q, (symbol.upper(), tf.upper())).fetchone()
    if not row:
        return None
    keys = ["id","symbol","tf","signal_key","status","entry","sl","tp1","tp2","tp3","opened_at","last_text","payload_json"]
    rec = dict(zip(keys, row))
    try:
        rec["payload"] = json.loads(rec["payload_json"]) if rec.get("payload_json") else None
    except Exception:
        rec["payload"] = None
    return rec

def create_signal(
    symbol: str, tf: str, *, entry: float, sl: float, tp_list: Tuple[float,float,float],
    text: str, payload: Dict[str, Any], db_path: str = DEFAULT_DB_PATH
) -> int:
    """
    สร้างสัญญาณสถานะ OPEN; กันซ้ำด้วย UNIQUE INDEX (symbol, tf, signal_key, status)
    คืนค่า:
      - lastrowid ถ้าสร้างใหม่
      - -1 ถ้าชน UNIQUE (ซ้ำ) → แปลว่ามีเรคอร์ด OPEN ที่เหมือนกันอยู่แล้ว
    """
    signal_key = build_signal_key(symbol, tf, entry, sl, tp_list[-1])
    now = int(time.time())
    with _conn(db_path) as c:
        cur = c.cursor()
        cur.execute(
            """INSERT OR IGNORE INTO signals
               (symbol, tf, signal_key, status, entry, sl, tp1, tp2, tp3, opened_at, last_text, payload_json)
               VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol.upper(), tf.upper(), signal_key, float(entry), float(sl),
             float(tp_list[0]), float(tp_list[1]), float(tp_list[2]),
             now, text, dumps_safe(payload)),
        )
        if cur.rowcount == 0:
            return -1
        return cur.lastrowid

def update_last_text(signal_id: int, text: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """อัปเดตข้อความล่าสุดที่ส่งไป LINE ให้สัญญาณนี้"""
    with _conn(db_path) as c:
        c.execute("UPDATE signals SET last_text=? WHERE id=?", (text, signal_id))

def close_signal(signal_id: int, outcome: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """ปิดสัญญาณ (CLOSED) พร้อมระบุผลลัพธ์: TP1|TP2|TP3|SL|MANUAL|CANCEL"""
    with _conn(db_path) as c:
        c.execute(
            "UPDATE signals SET status='CLOSED', outcome=?, closed_at=? WHERE id=? AND status='OPEN'",
            (outcome, int(time.time()), signal_id),
        )

# -----------------------------
# บล็อคจนกว่าได้ TP1
# -----------------------------
def is_blocked(symbol: str, tf: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT blocked FROM blocks WHERE symbol=? AND tf=?",
            (symbol.upper(), tf.upper())
        ).fetchone()
    return bool(row[0]) if row else False

def set_blocked(symbol: str, tf: str, blocked: bool, db_path: str = DEFAULT_DB_PATH) -> None:
    with _conn(db_path) as c:
        c.execute(
            """INSERT INTO blocks(symbol, tf, blocked, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(symbol, tf) DO UPDATE SET blocked=excluded.blocked, updated_at=excluded.updated_at""",
            (symbol.upper(), tf.upper(), 1 if blocked else 0, int(time.time()))
        )

def upsert_from_payload(symbol: str, tf: str, text: str, payload: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    รับ payload จาก wave_service → ตัด entry/tp/sl → กันยิงซ้ำ → ถ้าไม่มี OPEN เดิมให้สร้างใหม่
    *เพิ่มเงื่อนไข*: ถ้าถูกบล็อค (ต้องรอจนกว่า TP1) จะไม่สร้าง/ไม่ส่ง
    คืนค่า:
      {created: bool, skipped: bool, id: int|None, reason: str}
    """
    risk = (payload or {}).get("risk") or {}
    entry = risk.get("entry")
    tps = risk.get("tp") or []
    sl = risk.get("sl")
    if not isinstance(entry, (int, float)) or not isinstance(sl, (int, float)) or len(tps) < 3:
        return {"created": False, "skipped": True, "id": None, "reason": "missing entry/sl/tps"}

    # 0) เช็คบล็อคก่อน (ต้องรอจนกว่าจะได้ TP1)
    if is_blocked(symbol, tf, db_path=db_path):
        return {"created": False, "skipped": True, "id": None, "reason": "blocked_until_tp1"}

    # 1) กันยิงซ้ำระดับ OPEN (มีอยู่แล้วในคู่เดียวกัน/TF เดียวกัน)
    open_existing = get_open_signal(symbol, tf, db_path=db_path)
    if open_existing:
        return {"created": False, "skipped": True, "id": open_existing["id"], "reason": "open exists"}

    # 2) พยายามสร้างใหม่ (กันซ้ำด้วย signal_key อีกชั้น)
    sid = create_signal(
        symbol, tf,
        entry=entry, sl=sl, tp_list=(tps[0], tps[1], tps[2]),
        text=text, payload=payload, db_path=db_path
    )
    if sid == -1:
        return {"created": False, "skipped": True, "id": None, "reason": "duplicate signal_key"}
    return {"created": True, "skipped": False, "id": sid, "reason": "created"}
