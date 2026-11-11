"""Daily report builder.

Assembles the overnight report from real records. Sections with no data say
"no data recorded" rather than inventing content.
"""

from __future__ import annotations

import datetime
import time
from typing import Optional

from backend import analytics, characters as chars
from backend import scraper
from backend.config import get_config
from backend.db import db, log, recent_logs


def _tz():
    import datetime as _dt

    from backend.analytics import _tz as analytics_tz

    return analytics_tz()


def _fmt_ts(ts: Optional[float]) -> str:
    if not ts:
        return "never"
    return datetime.datetime.fromtimestamp(ts, _tz()).strftime("%Y-%m-%d %H:%M")


def build_daily_report() -> str:
    """Build the full overnight report text."""
    cfg = get_config()
    now = datetime.datetime.now(_tz())
    lines: list[str] = []
    lines.append("ETERNAL CABAL  NIGHT SHIFT REPORT")
    lines.append("")
    lines.append(f"Date: {now.strftime('%Y-%m-%d %H:%M %Z')}")

    # --- Server status ---
    snap = scraper.latest_snapshot()
    lines.append("")
    lines.append("Server status:")
    if snap:
        rates = snap.get("rates") or {}
        rate_str = ", ".join(f"{k} {v}" for k, v in rates.items()) or "n/a"
        lines.append(
            f"  Episode {snap.get('episode') or '?'} | Max Lvl {snap.get('max_level') or '?'}"
        )
        lines.append(f"  Rates: {rate_str}")
        lines.append(f"  Client: v{snap.get('client_version') or '?'} ({snap.get('client_updated') or '?'})")
        lines.append(f"  Last checked: {_fmt_ts(snap.get('fetched_at'))}")
    else:
        lines.append("  No snapshot recorded yet")

    # --- Announcements ---
    lines.append("")
    lines.append("Server announcements:")
    ann = recent_announcements(3)
    if ann:
        for a in ann:
            lines.append(f"  - {a.get('title') or a.get('source') or 'update'}")
    else:
        lines.append("  No new announcements detected")

    # --- Upcoming events ---
    lines.append("")
    lines.append("Upcoming events:")
    ev = upcoming_events(3)
    if ev:
        for e in ev:
            lines.append(f"  - {e.get('title')} ({e.get('starts_at') or 'date tbd'})")
    else:
        lines.append("  No events recorded")

    # --- Character progression ---
    lines.append("")
    lines.append("Character progression:")
    roster = chars.list_characters()
    if roster:
        for c in roster:
            lines.append(
                f"  {c['name']} - {c.get('class') or '?'} Lv.{c.get('level') or '?'}"
            )
    else:
        lines.append("  No characters recorded")

    # --- Farming ---
    lines.append("")
    lines.append("Recorded farming activity:")
    fs = analytics.farming_summary(days=1)
    if fs["session_count"]:
        lines.append(
            f"  {fs['session_count']} session(s), {fs['total_hours']:.2f}h, "
            f"{fs['total_exp']:.0f} EXP"
        )
        lines.append(f"  EXP/hour: {fs['exp_per_hour']:.0f}")
        lines.append(f"  Profit: {fs['profit']:.0f} Alz")
    else:
        lines.append("  No farming sessions recorded in the last 24h")

    # --- EXP statistics ---
    lines.append("")
    lines.append("EXP statistics:")
    week = analytics.farming_summary(days=7)
    if week["session_count"]:
        lines.append(
            f"  7d: {week['session_count']} sessions, {week['total_exp']:.0f} EXP, "
            f"{week['exp_per_hour']:.0f} EXP/h"
        )
        for loc, agg in week["by_location"].items():
            lines.append(
                f"    {loc}: {agg['sessions']} runs, {agg['exp_per_hour']:.0f} EXP/h"
            )
    else:
        lines.append("  No EXP data recorded in the last 7 days")

    # --- Item drops ---
    lines.append("")
    lines.append("Recorded item drops:")
    drops = recent_drops(5)
    if drops:
        for d in drops:
            lines.append(f"  - {d}")
    else:
        lines.append("  No drops recorded")

    # --- Market ---
    lines.append("")
    lines.append("Market updates:")
    mr = analytics.market_report()
    if mr["tracked_items"]:
        lines.append(f"  Tracking {mr['tracked_items']} item(s)")
        for ch in mr["changes"][:5]:
            direction = "+" if ch["delta"] >= 0 else ""
            lines.append(
                f"  {ch['name']}: {ch['current']:.0f} {ch['currency']} "
                f"({direction}{ch['percent']:.1f}%)"
            )
    else:
        lines.append("  No market data recorded")

    # --- Daily objectives ---
    lines.append("")
    lines.append("Daily objectives:")
    objs = analytics.list_objectives()
    if objs:
        for o in objs[:8]:
            mark = "[x]" if o.get("done") else "[ ]"
            who = o.get("character_name") or "General"
            lines.append(f"  {mark} {who}: {o.get('title')}")
    else:
        lines.append("  No objectives for today")

    # --- Application health ---
    lines.append("")
    lines.append("Application health:")
    health = service_health()
    lines.append(f"  Service: {health['status']}")
    lines.append(f"  Uptime: {health['uptime_human']}")
    lines.append(f"  Database: {health['database']}")
    lines.append(f"  Telegram: {health['telegram']}")
    lines.append(f"  Disk free: {health['disk_free_gb']:.1f} GB")

    # --- Warnings ---
    lines.append("")
    lines.append("Warnings:")
    warns = recent_logs(limit=20, level="WARNING") + recent_logs(limit=20, level="ERROR")
    warns = warns[:5]
    if warns:
        for w in warns:
            lines.append(f"  [{w['level']}] {w['component']}: {w['message'][:90]}")
    else:
        lines.append("  None")

    return "\n".join(lines)


def recent_announcements(limit: int = 5) -> list[dict]:
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY seen_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def upcoming_events(limit: int = 5) -> list[dict]:
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY starts_at ASC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def recent_drops(limit: int = 5) -> list[str]:
    """Flatten recent farming session items into a short list."""
    sessions = analytics.list_farming_sessions(limit=20)
    out: list[str] = []
    for s in sessions:
        for item in s.get("items") or []:
            if isinstance(item, dict):
                name = item.get("name") or str(item)
            else:
                name = str(item)
            out.append(name)
            if len(out) >= limit:
                return out
    return out


def service_health() -> dict:
    """Collect the health snapshot shown in the report and dashboard."""
    import os

    import psutil

    from backend.config import DB_PATH, HEARTBEAT_PATH
    from backend.notify import connection_status

    status = "unknown"
    started = None
    if HEARTBEAT_PATH.exists():
        try:
            import json

            hb = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
            started = hb.get("started_at")
            age = time.time() - float(hb.get("ts", 0))
            status = "running" if age < 300 else "stale"
        except Exception:
            status = "unreadable"

    uptime = (time.time() - started) if started else 0
    hours, rem = divmod(int(uptime), 3600)
    minutes = rem // 60

    db_ok = "ok"
    try:
        with db(readonly=True) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        db_ok = f"error: {exc}"

    tel = connection_status()
    tel_str = "reachable" if tel["reachable"] else "unreachable"

    try:
        free = psutil.disk_usage(str(DB_PATH.parent)).free / (1024 ** 3)
    except Exception:
        free = 0.0

    return {
        "status": status,
        "started_at": started,
        "uptime_seconds": uptime,
        "uptime_human": f"{hours}h {minutes}m",
        "database": db_ok,
        "telegram": tel_str,
        "telegram_detail": tel.get("detail", "")[:80],
        "disk_free_gb": free,
        "checked_at": time.time(),
    }


def record_announcement(source: str, title: str, body: str = "", url: str = "") -> bool:
    """Store an announcement if its hash is new. Returns True when new."""
    import hashlib

    hash_val = hashlib.sha256(f"{source}:{title}:{body}".encode()).hexdigest()[:24]
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM announcements WHERE hash=?", (hash_val,)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO announcements(source, title, body, url, seen_at, hash)"
            " VALUES(?,?,?,?,?,?)",
            (source, title, body, url, time.time(), hash_val),
        )
    log("announce", f"new announcement: {title}")
    return True


def record_event(title: str, starts_at: str = "", ends_at: str = "", description: str = "",
                 source: str = "") -> bool:
    """Store an event if an identical title+start does not already exist."""
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM events WHERE title=? AND starts_at=?", (title, starts_at)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO events(title, starts_at, ends_at, description, source, seen_at)"
            " VALUES(?,?,?,?,?,?)",
            (title, starts_at, ends_at, description, source, time.time()),
        )
    log("event", f"new event: {title}")
    return True
