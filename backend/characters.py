"""Character profile management."""

from __future__ import annotations

import json
import time
from typing import Optional

from backend.db import db, log


def add_character(
    name: str,
    class_name: str = "",
    level: int = 1,
    stats: Optional[dict] = None,
    equipment: Optional[list] = None,
    skills: Optional[list] = None,
    build: Optional[dict] = None,
    objectives: Optional[list] = None,
) -> int:
    now = time.time()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO characters"
            "(name, class, level, stats, equipment, skills, build, objectives,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                name, class_name, level, json.dumps(stats or {}),
                json.dumps(equipment or []), json.dumps(skills or []),
                json.dumps(build or {}), json.dumps(objectives or []), now, now,
            ),
        )
        cid = cur.lastrowid
    log("character", f"added character {name} (id={cid})")
    return cid


def update_character(character_id: int, **fields) -> bool:
    """Update whitelisted character fields."""
    allowed = {"name", "class", "level", "stats", "equipment", "skills", "build", "objectives"}
    sets = []
    values = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append(f"{key}=?")
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value))
        else:
            values.append(value)
    if not sets:
        return False
    sets.append("updated_at=?")
    values.append(time.time())
    values.append(character_id)
    with db() as conn:
        conn.execute(
            f"UPDATE characters SET {', '.join(sets)} WHERE id=?", values
        )
    log("character", f"updated character {character_id}")
    return True


def get_character(character_id: int) -> Optional[dict]:
    with db(readonly=True) as conn:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (character_id,)).fetchone()
    return _decode(dict(row)) if row else None


def list_characters() -> list[dict]:
    with db(readonly=True) as conn:
        rows = conn.execute("SELECT * FROM characters ORDER BY name").fetchall()
    return [_decode(dict(r)) for r in rows]


def delete_character(character_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM characters WHERE id=?", (character_id,))
    log("character", f"deleted character {character_id}")


def _decode(d: dict) -> dict:
    for field in ("stats", "equipment", "skills", "build", "objectives"):
        raw = d.get(field)
        if isinstance(raw, str):
            try:
                d[field] = json.loads(raw or "{}")
            except ValueError:
                d[field] = {} if field in ("stats", "build") else []
    return d


def character_progress(character_id: int) -> dict:
    """Summarise one character's recorded farming and objectives."""
    from backend import analytics

    char = get_character(character_id)
    if not char:
        return {"error": "character not found"}

    summary = analytics.farming_summary(days=30, character_id=character_id)
    objectives = analytics.list_objectives()
    mine = [o for o in objectives if o.get("character_id") == character_id]
    done = [o for o in mine if o.get("done")]

    return {
        "character": char,
        "farming_30d": summary,
        "today_objectives": mine,
        "today_done": len(done),
        "today_total": len(mine),
    }
