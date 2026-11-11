"""Farming and market analytics.

Every number here is derived from records the user entered. Nothing is
fabricated: if no sessions exist, the report says so.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from backend.db import db, log


# --- Farming ---------------------------------------------------------------

def add_farming_session(
    character_id: Optional[int],
    location: str,
    dungeon: str,
    started_at: float,
    ended_at: float,
    exp_gained: float,
    items: Optional[list] = None,
    consumables: Optional[list] = None,
    expenses: float = 0.0,
    revenue: float = 0.0,
    notes: str = "",
) -> int:
    """Record one farming session. Returns the new row id."""
    duration = max(0.0, (ended_at - started_at) / 60.0)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO farming_sessions"
            "(character_id, location, dungeon, started_at, ended_at, duration_min,"
            " exp_gained, items, consumables, expenses, revenue, notes)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                character_id, location, dungeon, started_at, ended_at, duration,
                exp_gained, json.dumps(items or []), json.dumps(consumables or []),
                expenses, revenue, notes,
            ),
        )
        sid = cur.lastrowid
    log("farming", f"session {sid} recorded: {location}/{dungeon} {duration:.0f}min")
    return sid


def farming_summary(days: int = 7, character_id: Optional[int] = None) -> dict:
    """Aggregate farming stats over the last N days.

    Returns zeros rather than invented numbers when nothing was recorded.
    """
    cutoff = time.time() - days * 86400
    with db(readonly=True) as conn:
        if character_id:
            rows = conn.execute(
                "SELECT * FROM farming_sessions WHERE started_at >= ? AND character_id=?",
                (cutoff, character_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM farming_sessions WHERE started_at >= ?", (cutoff,)
            ).fetchall()

    sessions = [dict(r) for r in rows]
    total_min = sum(s.get("duration_min") or 0 for s in sessions)
    total_exp = sum(s.get("exp_gained") or 0 for s in sessions)
    total_expenses = sum(s.get("expenses") or 0 for s in sessions)
    total_revenue = sum(s.get("revenue") or 0 for s in sessions)

    hours = total_min / 60.0
    exp_per_hour = (total_exp / hours) if hours > 0 else 0.0
    profit = total_revenue - total_expenses

    by_location: dict[str, dict] = {}
    for s in sessions:
        key = s.get("location") or "Unknown"
        agg = by_location.setdefault(
            key, {"sessions": 0, "minutes": 0.0, "exp": 0.0, "profit": 0.0}
        )
        agg["sessions"] += 1
        agg["minutes"] += s.get("duration_min") or 0
        agg["exp"] += s.get("exp_gained") or 0
        agg["profit"] += (s.get("revenue") or 0) - (s.get("expenses") or 0)

    for agg in by_location.values():
        h = agg["minutes"] / 60.0
        agg["exp_per_hour"] = (agg["exp"] / h) if h > 0 else 0.0

    return {
        "days": days,
        "session_count": len(sessions),
        "total_minutes": total_min,
        "total_hours": hours,
        "total_exp": total_exp,
        "exp_per_hour": exp_per_hour,
        "total_expenses": total_expenses,
        "total_revenue": total_revenue,
        "profit": profit,
        "by_location": by_location,
        "sessions": sessions,
    }


def list_farming_sessions(limit: int = 50, character_id: Optional[int] = None) -> list[dict]:
    with db(readonly=True) as conn:
        if character_id:
            rows = conn.execute(
                "SELECT * FROM farming_sessions WHERE character_id=? "
                "ORDER BY started_at DESC LIMIT ?",
                (character_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM farming_sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for field in ("items", "consumables"):
            try:
                d[field] = json.loads(d.get(field) or "[]")
            except ValueError:
                d[field] = []
        out.append(d)
    return out


# --- Market ----------------------------------------------------------------

def add_market_item(
    name: str,
    price: float,
    category: str = "",
    currency: str = "Alz",
    source: str = "manual",
    notes: str = "",
    recorded_at: Optional[float] = None,
) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO market_items(name, category, price, currency, source,"
            " recorded_at, notes) VALUES(?,?,?,?,?,?,?)",
            (name, category, price, currency, source,
             recorded_at if recorded_at is not None else time.time(), notes),
        )
        iid = cur.lastrowid
    log("market", f"price recorded: {name} = {price} {currency}")
    return iid


def market_prices(name: Optional[str] = None, limit: int = 100) -> list[dict]:
    with db(readonly=True) as conn:
        if name:
            rows = conn.execute(
                "SELECT * FROM market_items WHERE name LIKE ? "
                "ORDER BY recorded_at DESC LIMIT ?",
                (f"%{name}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM market_items ORDER BY recorded_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def price_history(name: str) -> list[dict]:
    """Chronological price history for one item."""
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT recorded_at, price, currency, source FROM market_items "
            "WHERE name LIKE ? ORDER BY recorded_at ASC",
            (f"%{name}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def price_change(name: str) -> Optional[dict]:
    """Compare the latest price against the previous recorded price."""
    hist = price_history(name)
    if len(hist) < 2:
        return None
    prev, cur = hist[-2], hist[-1]
    if not prev["price"]:
        return None
    delta = cur["price"] - prev["price"]
    pct = (delta / prev["price"]) * 100 if prev["price"] else 0.0
    return {
        "name": name,
        "previous": prev["price"],
        "current": cur["price"],
        "delta": delta,
        "percent": pct,
        "currency": cur.get("currency") or "Alz",
    }


def market_report() -> dict:
    """Summarise distinct tracked items and their latest price movement."""
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT name, MAX(recorded_at) AS latest FROM market_items "
            "GROUP BY name ORDER BY name"
        ).fetchall()
    names = [r["name"] for r in rows]
    changes = []
    for n in names:
        ch = price_change(n)
        if ch:
            changes.append(ch)
    return {"tracked_items": len(names), "names": names, "changes": changes}


# --- Objectives ------------------------------------------------------------

def refresh_daily_objectives(character_id: Optional[int] = None) -> list[dict]:
    """Create today's objective rows from character objectives.

    Idempotent: re-running on the same day does not duplicate rows.
    """
    import datetime

    tz = _tz()
    today = datetime.datetime.now(tz).date().isoformat()
    created: list[dict] = []

    with db(readonly=True) as conn:
        if character_id:
            chars = conn.execute(
                "SELECT * FROM characters WHERE id=?", (character_id,)
            ).fetchall()
        else:
            chars = conn.execute("SELECT * FROM characters").fetchall()

    with db() as conn:
        for c in chars:
            existing = conn.execute(
                "SELECT COUNT(*) AS n FROM daily_objectives "
                "WHERE character_id=? AND objective_date=?",
                (c["id"], today),
            ).fetchone()["n"]
            if existing:
                continue
            raw = c["objectives"]
            if isinstance(raw, str):
                try:
                    objectives = json.loads(raw or "[]")
                except ValueError:
                    objectives = []
            elif isinstance(raw, list):
                objectives = raw
            else:
                objectives = []
            if not isinstance(objectives, list):
                objectives = []
            for obj in objectives[:5]:
                title = obj if isinstance(obj, str) else str(obj)
                conn.execute(
                    "INSERT INTO daily_objectives"
                    "(character_id, objective_date, kind, title, created_at)"
                    " VALUES(?,?,?,?,?)",
                    (c["id"], today, "progression", title, time.time()),
                )
                created.append(
                    {"character_id": c["id"], "title": title, "date": today}
                )
    if created:
        log("objectives", f"created {len(created)} objectives for {today}")
    return created


def list_objectives(date: Optional[str] = None) -> list[dict]:
    import datetime

    tz = _tz()
    day = date or datetime.datetime.now(tz).date().isoformat()
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT d.*, c.name AS character_name FROM daily_objectives d "
            "LEFT JOIN characters c ON c.id = d.character_id "
            "WHERE d.objective_date=? ORDER BY d.id",
            (day,),
        ).fetchall()
    return [dict(r) for r in rows]


def complete_objective(objective_id: int, done: bool = True) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE daily_objectives SET done=? WHERE id=?",
            (1 if done else 0, objective_id),
        )


def _tz():
    """Return the configured timezone as a tzinfo object."""
    import datetime

    from backend.config import get_config

    name = get_config().get("timezone", "Asia/Manila")
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        return datetime.timezone(datetime.timedelta(hours=8))
