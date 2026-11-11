"""SQLite persistence layer for the Night Shift companion.

Single file, WAL mode, short timeouts. The companion is the only writer during
normal operation; the dashboard opens read-only connections.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.config import DB_PATH, ensure_dirs

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS characters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    class         TEXT,
    level         INTEGER DEFAULT 1,
    stats         TEXT DEFAULT '{}',
    equipment     TEXT DEFAULT '[]',
    skills        TEXT DEFAULT '[]',
    build         TEXT DEFAULT '{}',
    objectives    TEXT DEFAULT '[]',
    created_at    REAL,
    updated_at    REAL
);

CREATE TABLE IF NOT EXISTS farming_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id  INTEGER,
    location      TEXT,
    dungeon       TEXT,
    started_at    REAL,
    ended_at      REAL,
    duration_min  REAL,
    exp_gained    REAL,
    items         TEXT DEFAULT '[]',
    consumables   TEXT DEFAULT '[]',
    expenses      REAL DEFAULT 0,
    revenue       REAL DEFAULT 0,
    notes         TEXT,
    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS market_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    category      TEXT,
    price         REAL,
    currency      TEXT DEFAULT 'Alz',
    source        TEXT,
    recorded_at   REAL,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS server_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at    REAL,
    episode       TEXT,
    max_level     TEXT,
    rates         TEXT DEFAULT '{}',
    client_version TEXT,
    client_size   TEXT,
    client_updated TEXT,
    raw_hash      TEXT,
    page          TEXT
);

CREATE TABLE IF NOT EXISTS announcements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT,
    title         TEXT,
    body          TEXT,
    url           TEXT,
    seen_at       REAL,
    hash          TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT,
    starts_at     TEXT,
    ends_at       TEXT,
    description   TEXT,
    source        TEXT,
    seen_at       REAL
);

CREATE TABLE IF NOT EXISTS daily_objectives (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id  INTEGER,
    objective_date TEXT,
    kind          TEXT,
    title         TEXT,
    done          INTEGER DEFAULT 0,
    created_at    REAL
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key       TEXT UNIQUE,
    label         TEXT,
    schedule      TEXT,
    last_run      REAL,
    next_run      REAL,
    last_status   TEXT,
    last_error    TEXT,
    enabled       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS service_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL,
    level         TEXT,
    component     TEXT,
    message       TEXT
);

CREATE TABLE IF NOT EXISTS backups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    REAL,
    path          TEXT,
    size_bytes    INTEGER,
    checksum      TEXT,
    verified      INTEGER DEFAULT 0,
    kind          TEXT DEFAULT 'daily'
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_farming_char ON farming_sessions(character_id);
CREATE INDEX IF NOT EXISTS idx_farming_start ON farming_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_market_name ON market_items(name);
CREATE INDEX IF NOT EXISTS idx_snap_time ON server_snapshots(fetched_at);
CREATE INDEX IF NOT EXISTS idx_log_time ON service_log(ts);
"""


def connect(path: Optional[str] = None, readonly: bool = False) -> sqlite3.Connection:
    """Open a SQLite connection with sane concurrency settings."""
    ensure_dirs()
    target = path or str(DB_PATH)
    # A redirected test database may live outside the project tree.
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        uri = f"file:{target}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        conn = sqlite3.connect(target, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db(path: Optional[str] = None, readonly: bool = False):
    """Transaction context manager: commit on success, rollback on error."""
    conn = connect(path, readonly=readonly)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the schema if it does not exist yet."""
    with db() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        _seed_jobs(conn)


def _seed_jobs(conn: sqlite3.Connection) -> None:
    """Register the built-in scheduled jobs once."""
    jobs = [
        ("server_monitor", "Server monitor", "every 30 min"),
        ("daily_report", "Daily Telegram report", "daily 06:00"),
        ("daily_backup", "Daily backup", "daily 05:30"),
        ("farming_summary", "Farming summary", "daily 06:05"),
        ("objectives_refresh", "Daily objectives refresh", "daily 05:45"),
        ("health_check", "Health check", "every 5 min"),
    ]
    for key, label, schedule in jobs:
        conn.execute(
            "INSERT OR IGNORE INTO scheduled_jobs(job_key, label, schedule) VALUES(?,?,?)",
            (key, label, schedule),
        )


def get_setting(key: str, default: Any = None) -> Any:
    with db(readonly=True) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return row["value"]


def set_setting(key: str, value: Any) -> None:
    payload = json.dumps(value) if not isinstance(value, str) else value
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, payload),
        )


def log(component: str, message: str, level: str = "INFO") -> None:
    """Append a line to the service log (best effort, never raises)."""
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO service_log(ts, level, component, message) VALUES(?,?,?,?)",
                (time.time(), level, component, message),
            )
    except Exception:
        pass


def recent_logs(limit: int = 200, level: Optional[str] = None) -> list[dict]:
    with db(readonly=True) as conn:
        if level:
            rows = conn.execute(
                "SELECT ts, level, component, message FROM service_log "
                "WHERE level=? ORDER BY id DESC LIMIT ?",
                (level, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts, level, component, message FROM service_log "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def prune_logs(keep_days: int = 30) -> int:
    """Delete log rows older than keep_days. Returns rows removed."""
    cutoff = time.time() - keep_days * 86400
    with db() as conn:
        cur = conn.execute("DELETE FROM service_log WHERE ts < ?", (cutoff,))
        return cur.rowcount or 0
