"""SQLite storage. One file: data/careeros.db."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone

from .config import DB_PATH

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT UNIQUE NOT NULL,
  source TEXT, kind TEXT, title TEXT, org TEXT, location TEXT, country TEXT,
  url TEXT, apply_url TEXT, posted TEXT, deadline TEXT, salary TEXT,
  description TEXT, track TEXT, score INTEGER DEFAULT 0, reasons TEXT,
  sponsorship TEXT, eligibility TEXT,
  status TEXT DEFAULT 'new',
  notes TEXT DEFAULT '',
  contact TEXT DEFAULT '',
  submitted_at TEXT, last_contact_at TEXT, followup_at TEXT,
  created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opp_score ON opportunities(score);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opp_id INTEGER, kind TEXT, detail TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_opp ON events(opp_id);

CREATE TABLE IF NOT EXISTS agents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE, kind TEXT, config TEXT, enabled INTEGER DEFAULT 1,
  on_schedule INTEGER DEFAULT 1,
  last_run TEXT, last_status TEXT, last_found INTEGER DEFAULT 0,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id INTEGER, agent_name TEXT, started_at TEXT, finished_at TEXT,
  status TEXT, found INTEGER DEFAULT 0, log TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE, label TEXT, value TEXT, source TEXT,
  uses INTEGER DEFAULT 0, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opp_id INTEGER, label TEXT, filled TEXT, final TEXT, fill_source TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
  key TEXT PRIMARY KEY, ok INTEGER, working_slug TEXT, detail TEXT, checked_at TEXT
);

CREATE TABLE IF NOT EXISTS learn_progress (
  module_id TEXT PRIMARY KEY, status TEXT, notes TEXT DEFAULT '', updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id TEXT, payload TEXT, answers TEXT, grade TEXT, score REAL, created_at TEXT
);

CREATE TABLE IF NOT EXISTS emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  msg_id TEXT UNIQUE, opp_id INTEGER, sender TEXT, subject TEXT, received_at TEXT,
  category TEXT, snippet TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE, title TEXT, body TEXT, created_at TEXT, seen INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fill_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opp_id INTEGER, url TEXT, status TEXT DEFAULT 'pending', created_at TEXT
);

CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT, purpose TEXT, detail TEXT, ok INTEGER,
  input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cache_tokens INTEGER DEFAULT 0,
  web_searches INTEGER DEFAULT 0, turns INTEGER DEFAULT 0, duration_ms INTEGER DEFAULT 0, api_equiv_usd REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_at ON usage(at);

CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=30000")
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


def q(sql: str, params: tuple | list = ()) -> list[dict]:
    with _lock:
        cur = conn().execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def q1(sql: str, params: tuple | list = ()) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def x(sql: str, params: tuple | list = ()) -> int:
    for attempt in range(5):
        try:
            with _lock:
                cur = conn().execute(sql, params)
                conn().commit()
                return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount
        except sqlite3.OperationalError as e:  # database is locked (another process)
            if "locked" not in str(e) or attempt == 4:
                raise
            time.sleep(0.5 * (attempt + 1))
    return 0


def kv_get(k: str, default=None):
    r = q1("SELECT v FROM kv WHERE k=?", (k,))
    return json.loads(r["v"]) if r else default


def kv_set(k: str, v) -> None:
    x("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))


def event(opp_id: int | None, kind: str, detail: str = "") -> None:
    x("INSERT INTO events(opp_id,kind,detail,created_at) VALUES(?,?,?,?)", (opp_id, kind, detail[:4000], now()))


def repair_v4() -> None:
    """One-time clean-up of two bugs in earlier versions:
    - tick-box answers ('checked') were learned under the same name as text boxes (e.g. 'Email')
    - clicking a job page's 'Apply' button was taken as submitting the application."""
    if kv_get("repair_v4"):
        return
    bad = x("DELETE FROM answers WHERE key NOT LIKE '[tick] %' AND lower(trim(value)) IN "
            "('checked','unchecked','true','false','on','off')")
    rows = q("SELECT DISTINCT o.id FROM opportunities o JOIN events e ON e.opp_id=o.id "
             "WHERE o.status='submitted' AND e.kind='status' AND e.detail='submitted - you clicked submit'")
    for r in rows:
        x("UPDATE opportunities SET status='filling', submitted_at=NULL, updated_at=? WHERE id=?", (now(), r["id"]))
        event(r["id"], "status", "filling - un-marked: an older version mistook the page's Apply button for Submit. "
                                 "If you did submit it, Gmail tracking will mark it again from the confirmation email.")
    kv_set("repair_v4", {"at": now(), "answers_removed": bad, "unmarked": len(rows)})


def set_status(opp_id: int, status: str, detail: str = "") -> None:
    fields = {"status": status, "updated_at": now()}
    if status == "submitted":
        r = q1("SELECT submitted_at FROM opportunities WHERE id=?", (opp_id,))
        if r and not r["submitted_at"]:
            fields["submitted_at"] = now()
    sets = ",".join(f"{k}=?" for k in fields)
    x(f"UPDATE opportunities SET {sets} WHERE id=?", (*fields.values(), opp_id))
    event(opp_id, "status", f"{status}{(' - ' + detail) if detail else ''}")


def notify_once(key: str, title: str, body: str) -> bool:
    """Record a notification; returns True only the first time this key is seen."""
    try:
        with _lock:
            conn().execute("INSERT INTO notifications(key,title,body,created_at) VALUES(?,?,?,?)",
                           (key, title, body, now()))
            conn().commit()
        return True
    except sqlite3.IntegrityError:
        return False
