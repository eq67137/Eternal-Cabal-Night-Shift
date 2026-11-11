"""Dashboard backend - FastAPI application.

Reads and writes the same SQLite database the companion uses. Opening the
dashboard never starts a second service instance.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend import analytics, backup, characters, notify, report, scraper  # noqa: E402
from backend.config import (  # noqa: E402
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    FRONTEND_DIR,
    STATE_PATH,
    ensure_dirs,
    get_config,
    save_config,
)
from backend.db import db, init_db, log, recent_logs  # noqa: E402
from backend.instance import read_heartbeat  # noqa: E402

app = FastAPI(title="Eternal Cabal Night Shift", version="1.0.0")


# --- Request models --------------------------------------------------------

class CharacterIn(BaseModel):
    name: str
    class_name: str = ""
    level: int = 1
    stats: dict = {}
    equipment: list = []
    skills: list = []
    build: dict = {}
    objectives: list = []


class FarmingIn(BaseModel):
    character_id: Optional[int] = None
    location: str = ""
    dungeon: str = ""
    started_at: float
    ended_at: float
    exp_gained: float = 0
    items: list = []
    consumables: list = []
    expenses: float = 0
    revenue: float = 0
    notes: str = ""


class MarketIn(BaseModel):
    name: str
    price: float
    category: str = ""
    currency: str = "Alz"
    source: str = "manual"
    notes: str = ""


class SettingsIn(BaseModel):
    daily_report_hour: Optional[int] = None
    daily_report_minute: Optional[int] = None
    server_poll_interval_min: Optional[int] = None
    cache_ttl_seconds: Optional[int] = None
    backup_retention_days: Optional[int] = None
    dashboard_port: Optional[int] = None


# --- Bootstrap -------------------------------------------------------------

@app.on_event("startup")
def _startup() -> None:
    ensure_dirs()
    init_db()


# --- Health / service ------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    h = report.service_health()
    hb = read_heartbeat()
    h["heartbeat"] = hb
    h["pid"] = os.getpid()
    return h


@app.get("/api/service/status")
def service_status() -> dict:
    hb = read_heartbeat()
    if not hb:
        return {"running": False, "detail": "no heartbeat file"}
    age = time.time() - float(hb.get("ts", 0))
    return {
        "running": age < 300,
        "stale": 300 <= age < 1800,
        "age_seconds": age,
        "pid": hb.get("pid"),
        "started_at": hb.get("started_at"),
        "extra": hb.get("extra", {}),
    }


@app.post("/api/service/{action}")
def service_control(action: str) -> dict:
    """Request start/stop/restart. Stop is honoured by the service loop."""
    if action not in ("stop", "restart", "start"):
        raise HTTPException(400, "unknown action")

    if action == "stop":
        STATE_PATH.write_text(json.dumps({"command": "stop"}), encoding="utf-8")
        log("dashboard", "stop requested from dashboard")
        return {"ok": True, "action": action}

    if action == "restart":
        # Stop first; the scheduled task's restart policy brings it back.
        STATE_PATH.write_text(json.dumps({"command": "stop"}), encoding="utf-8")
        log("dashboard", "restart requested from dashboard")
        return {"ok": True, "action": action}

    if action == "start":
        # Launch the service detached; never in-process.
        import subprocess

        from backend.config import ROOT

        script = ROOT / "backend" / "service.py"
        python = sys.executable
        subprocess.Popen(
            [python, str(script)],
            cwd=str(ROOT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        log("dashboard", "start requested from dashboard")
        return {"ok": True, "action": action}

    return {"ok": False}


# --- Server monitor --------------------------------------------------------

@app.get("/api/server/current")
def server_current() -> dict:
    return scraper.latest_snapshot() or {}


@app.get("/api/server/history")
def server_history(limit: int = 30) -> list:
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM server_snapshots ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["rates"] = json.loads(d.get("rates") or "{}")
        except ValueError:
            d["rates"] = {}
        out.append(d)
    return out


@app.post("/api/server/refresh")
def server_refresh() -> dict:
    prev = scraper.latest_snapshot()
    cur = scraper.snapshot_server()
    return {"snapshot": cur, "changes": scraper.snapshot_changes(prev, cur)}


@app.get("/api/server/announcements")
def announcements(limit: int = 20) -> list:
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY seen_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/server/events")
def events(limit: int = 20) -> list:
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY starts_at ASC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- Characters ------------------------------------------------------------

@app.get("/api/characters")
def list_characters() -> list:
    return characters.list_characters()


@app.get("/api/characters/{character_id}")
def get_character(character_id: int) -> dict:
    c = characters.get_character(character_id)
    if not c:
        raise HTTPException(404, "character not found")
    return characters.character_progress(character_id)


@app.post("/api/characters")
def create_character(payload: CharacterIn) -> dict:
    cid = characters.add_character(
        name=payload.name,
        class_name=payload.class_name,
        level=payload.level,
        stats=payload.stats,
        equipment=payload.equipment,
        skills=payload.skills,
        build=payload.build,
        objectives=payload.objectives,
    )
    return {"id": cid, "ok": True}


@app.patch("/api/characters/{character_id}")
def update_character(character_id: int, payload: dict) -> dict:
    characters.update_character(character_id, **payload)
    return {"ok": True}


@app.delete("/api/characters/{character_id}")
def delete_character(character_id: int) -> dict:
    characters.delete_character(character_id)
    return {"ok": True}


# --- Farming ---------------------------------------------------------------

@app.get("/api/farming/summary")
def farming_summary(days: int = 7, character_id: Optional[int] = None) -> dict:
    return analytics.farming_summary(days=days, character_id=character_id)


@app.get("/api/farming/sessions")
def farming_sessions(limit: int = 50, character_id: Optional[int] = None) -> list:
    return analytics.list_farming_sessions(limit=limit, character_id=character_id)


@app.post("/api/farming/sessions")
def create_farming_session(payload: FarmingIn) -> dict:
    sid = analytics.add_farming_session(**payload.model_dump())
    return {"id": sid, "ok": True}


# --- Market ----------------------------------------------------------------

@app.get("/api/market/items")
def market_items(name: Optional[str] = None, limit: int = 100) -> list:
    return analytics.market_prices(name=name, limit=limit)


@app.get("/api/market/report")
def market_report() -> dict:
    return analytics.market_report()


@app.get("/api/market/history")
def market_history(name: str) -> list:
    return analytics.price_history(name)


@app.post("/api/market/items")
def create_market_item(payload: MarketIn) -> dict:
    iid = analytics.add_market_item(**payload.model_dump())
    return {"id": iid, "ok": True}


# --- Objectives ------------------------------------------------------------

@app.get("/api/objectives")
def objectives(date: Optional[str] = None) -> list:
    return analytics.list_objectives(date=date)


@app.post("/api/objectives/refresh")
def objectives_refresh() -> dict:
    return {"created": analytics.refresh_daily_objectives()}


@app.post("/api/objectives/{objective_id}")
def objective_complete(objective_id: int, done: bool = True) -> dict:
    analytics.complete_objective(objective_id, done)
    return {"ok": True}


# --- Reports ---------------------------------------------------------------

@app.get("/api/reports/daily")
def daily_report() -> dict:
    return {"text": report.build_daily_report()}


@app.post("/api/reports/daily/send")
def daily_report_send() -> dict:
    text = report.build_daily_report()
    ok = notify.send_daily_report(text)
    return {"ok": ok}


@app.get("/api/reports/logs")
def logs(limit: int = 200, level: Optional[str] = None) -> list:
    return recent_logs(limit=limit, level=level)


# --- Scheduler -------------------------------------------------------------

@app.get("/api/scheduler/jobs")
def scheduler_jobs() -> list:
    from backend.service import build_scheduler

    return build_scheduler().job_status()


@app.post("/api/scheduler/{job_key}/run")
def scheduler_run(job_key: str) -> dict:
    from backend.service import build_scheduler

    ok = build_scheduler().run_now(job_key)
    return {"ok": ok}


@app.post("/api/scheduler/{job_key}/toggle")
def scheduler_toggle(job_key: str, enabled: bool = True) -> dict:
    from backend.service import build_scheduler

    build_scheduler().set_enabled(job_key, enabled)
    return {"ok": True}


# --- Backups ---------------------------------------------------------------

@app.get("/api/backups")
def backups() -> list:
    return backup.list_backups()


@app.post("/api/backups/run")
def backups_run() -> dict:
    result = backup.run_backup("manual")
    return result or {"ok": False, "error": "backup failed"}


@app.post("/api/backups/{backup_id}/verify")
def backups_verify(backup_id: int) -> dict:
    return {"ok": backup.verify_backup(backup_id)}


@app.post("/api/backups/{backup_id}/restore")
def backups_restore(backup_id: int) -> dict:
    return {"ok": backup.restore_backup(backup_id)}


# --- Settings --------------------------------------------------------------

@app.get("/api/settings")
def settings() -> dict:
    return get_config()


@app.post("/api/settings")
def update_settings(payload: SettingsIn) -> dict:
    cfg = get_config()
    for key, value in payload.model_dump().items():
        if value is not None:
            cfg[key] = value
    save_config(cfg)
    log("dashboard", "settings updated")
    return cfg


# --- Telegram --------------------------------------------------------------

@app.get("/api/telegram/status")
def telegram_status() -> dict:
    return notify.connection_status()


@app.post("/api/telegram/test")
def telegram_test() -> dict:
    ok = notify.send_message(
        "Night Shift test message. If you see this, reporting is working.",
        subject="ETERNAL CABAL - TEST",
    )
    return {"ok": ok}


# --- Static frontend -------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def main() -> None:
    import uvicorn

    cfg = get_config()
    host = cfg.get("dashboard_host", DASHBOARD_HOST)
    port = int(cfg.get("dashboard_port", DASHBOARD_PORT))
    log("dashboard", f"starting on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
