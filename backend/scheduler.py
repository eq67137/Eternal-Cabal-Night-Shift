"""Job scheduler.

A small, dependency-free scheduler built on a SQLite-backed job table. It is
deliberately not APScheduler: the companion must run on a modest PC with no
extra packages, and the job set is fixed and small.

Each job records last_run/next_run so a missed run while the PC was asleep is
executed once on resume, never repeatedly.
"""

from __future__ import annotations

import datetime
import time
from typing import Callable, Optional

from backend.db import db, log

JobFunc = Callable[[], None]


class Scheduler:
    """Runs registered jobs on interval or daily schedules."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._running = False

    def register(
        self,
        key: str,
        label: str,
        schedule: str,
        func: JobFunc,
    ) -> None:
        """Register a job. schedule is 'every N min' or 'daily HH:MM'."""
        self._jobs[key] = {
            "key": key,
            "label": label,
            "schedule": schedule,
            "func": func,
        }
        with db() as conn:
            conn.execute(
                "INSERT INTO scheduled_jobs(job_key, label, schedule) VALUES(?,?,?) "
                "ON CONFLICT(job_key) DO UPDATE SET label=excluded.label, "
                "schedule=excluded.schedule",
                (key, label, schedule),
            )
        log("scheduler", f"registered job {key} ({schedule})")

    # --- schedule parsing --------------------------------------------------

    @staticmethod
    def next_run_after(schedule: str, after: datetime.datetime) -> datetime.datetime:
        """Compute the next fire time strictly after `after`."""
        schedule = (schedule or "").strip().lower()
        if schedule.startswith("every"):
            minutes = int(schedule.split()[-2])
            return after + datetime.timedelta(minutes=minutes)
        if schedule.startswith("daily"):
            parts = schedule.split()
            hh, mm = 0, 0
            if len(parts) > 1 and ":" in parts[1]:
                hh, mm = (int(x) for x in parts[1].split(":")[:2])
            nxt = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if nxt <= after:
                nxt += datetime.timedelta(days=1)
            return nxt
        # Unknown schedule: retry in an hour, never spin.
        return after + datetime.timedelta(hours=1)

    @staticmethod
    def due(
        schedule: str,
        last_run: Optional[float],
        now: Optional[float] = None,
    ) -> bool:
        """True when the job should run now."""
        now = now or time.time()
        if not last_run:
            return True
        last_dt = datetime.datetime.fromtimestamp(last_run)
        nxt = Scheduler.next_run_after(schedule, last_dt)
        return now >= nxt.timestamp()

    # --- execution ----------------------------------------------------------

    def run_due(self, now: Optional[float] = None) -> list[str]:
        """Execute every due job once. Returns the keys that ran."""
        now = now or time.time()
        ran: list[str] = []
        with db(readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE enabled=1"
            ).fetchall()
        for row in rows:
            job = self._jobs.get(row["job_key"])
            if not job:
                continue
            if not self.due(row["schedule"], row["last_run"], now):
                continue
            self._execute(job, row, now)
            ran.append(job["key"])
        return ran

    def _execute(self, job: dict, row, now: float) -> None:
        key = job["key"]
        log("scheduler", f"running job {key}")
        try:
            job["func"]()
        except Exception as exc:
            log("scheduler", f"job {key} failed: {exc}", "ERROR")
            with db() as conn:
                conn.execute(
                    "UPDATE scheduled_jobs SET last_run=?, last_status='error', "
                    "last_error=? WHERE job_key=?",
                    (now, str(exc)[:300], key),
                )
            return
        nxt = self.next_run_after(row["schedule"], datetime.datetime.fromtimestamp(now))
        with db() as conn:
            conn.execute(
                "UPDATE scheduled_jobs SET last_run=?, next_run=?, last_status='ok', "
                "last_error=NULL WHERE job_key=?",
                (now, nxt.timestamp(), key),
            )

    def job_status(self) -> list[dict]:
        with db(readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_jobs ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def set_enabled(self, key: str, enabled: bool) -> None:
        with db() as conn:
            conn.execute(
                "UPDATE scheduled_jobs SET enabled=? WHERE job_key=?",
                (1 if enabled else 0, key),
            )

    def run_now(self, key: str) -> bool:
        """Force a job to run immediately, bypassing its schedule."""
        with db(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE job_key=?", (key,)
            ).fetchone()
        job = self._jobs.get(key)
        if not job or not row:
            return False
        self._execute(job, row, time.time())
        return True
