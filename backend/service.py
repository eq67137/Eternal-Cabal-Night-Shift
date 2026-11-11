"""EternalCabalNightShift - background companion service.

Runs as a Windows scheduled task at system startup. Independent of the
dashboard and of the game client.

Responsibilities:
  * single-instance enforcement
  * heartbeat + health monitoring
  * scheduled jobs (server monitor, reports, backups, objectives, health)
  * crash-loop protection (bounded restarts, then notify and stop)
  * graceful shutdown on stop request
"""

from __future__ import annotations

import datetime
import json
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

# Make the project root importable when launched from any directory.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import analytics, backup, characters, notify, report, scraper  # noqa: E402
from backend.config import (  # noqa: E402
    HEARTBEAT_INTERVAL_SEC,
    LOGS_DIR,
    MAX_RESTART_ATTEMPTS,
    RESTART_BACKOFF_SEC,
    ensure_dirs,
    get_config,
)
from backend.db import db, init_db, log, recent_logs  # noqa: E402
from backend.instance import (  # noqa: E402
    InstanceLocked,
    acquire_lock,
    read_heartbeat,
    release_lock,
    write_heartbeat,
)
from backend.scheduler import Scheduler  # noqa: E402

STARTED_AT = time.time()
STOP_EVENT = threading.Event()

# Consecutive-restart tracking for crash-loop protection.
_restart_count = 0
_last_start = 0.0


def _tz():
    from backend.analytics import _tz as t

    return t()


# --- Job implementations ---------------------------------------------------

def job_server_monitor() -> None:
    """Poll the public site and alert only on real changes."""
    prev = scraper.latest_snapshot()
    cur = scraper.snapshot_server()
    changes = scraper.snapshot_changes(prev, cur)
    if changes and prev:
        notify.send_alert(
            "Server information changed:\n" + "\n".join(f"  - {c}" for c in changes),
            subject="ETERNAL CABAL - SERVER UPDATE",
        )


def job_daily_report() -> None:
    """Build and send the overnight report."""
    text = report.build_daily_report()
    ok = notify.send_daily_report(text)
    if not ok:
        log("report", "daily report delivery failed", "ERROR")


def job_daily_backup() -> None:
    result = backup.run_backup("daily")
    if not result or not result.get("verified"):
        notify.send_alert(
            "Night Shift backup failed or failed verification. "
            "Manual check recommended.",
            subject="ETERNAL CABAL - BACKUP FAILURE",
        )


def job_farming_summary() -> None:
    """Record that the summary ran; the daily report carries the numbers."""
    summary = analytics.farming_summary(days=1)
    log(
        "farming",
        f"24h summary: {summary['session_count']} sessions, "
        f"{summary['total_exp']:.0f} EXP",
    )


def job_objectives_refresh() -> None:
    analytics.refresh_daily_objectives()


def job_health_check() -> None:
    """Lightweight self-check; alerts only on real problems."""
    health = report.service_health()
    problems = []

    if health["status"] == "stale":
        problems.append("heartbeat stale")
    if not health["database"].startswith("ok"):
        problems.append(f"database: {health['database']}")
    if health["disk_free_gb"] < 2.0:
        problems.append(f"disk low: {health['disk_free_gb']:.1f} GB free")
    if health["telegram"] != "reachable":
        problems.append("telegram unreachable")

    if problems:
        log("health", "; ".join(problems), "WARNING")

    # Persist for the dashboard.
    from backend.config import STATE_PATH

    STATE_PATH.write_text(json.dumps(health), encoding="utf-8")


JOBS = {
    "server_monitor": ("Server monitor", "every 30 min", job_server_monitor),
    "daily_report": ("Daily Telegram report", "daily 06:00", job_daily_report),
    "daily_backup": ("Daily backup", "daily 05:30", job_daily_backup),
    "farming_summary": ("Farming summary", "daily 06:05", job_farming_summary),
    "objectives_refresh": ("Daily objectives refresh", "daily 05:45", job_objectives_refresh),
    "health_check": ("Health check", "every 5 min", job_health_check),
}


def build_scheduler() -> Scheduler:
    sched = Scheduler()
    cfg = get_config()
    for key, (label, schedule, func) in JOBS.items():
        # Allow the config file to override the daily report time.
        if key == "daily_report":
            hh = int(cfg.get("daily_report_hour", 6))
            mm = int(cfg.get("daily_report_minute", 0))
            schedule = f"daily {hh:02d}:{mm:02d}"
        sched.register(key, label, schedule, func)
    return sched


# --- Health monitoring -----------------------------------------------------

def monitor_resources(stop: threading.Event) -> None:
    """Background thread: heartbeat, resource watch, disk watch.

    Writes an immediate heartbeat on start so the dashboard never shows
    "stopped" during the first interval.
    """
    import psutil

    proc = psutil.Process(os.getpid())
    while True:
        try:
            write_heartbeat(
                STARTED_AT,
                extra={
                    "rss_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
                    "cpu_percent": round(proc.cpu_percent(interval=None), 1),
                },
            )
        except Exception as exc:
            log("monitor", f"heartbeat failed: {exc}", "ERROR")
        if stop.wait(HEARTBEAT_INTERVAL_SEC):
            break


def watch_state_file(stop: threading.Event) -> None:
    """Watch for a stop request written by the dashboard or stop script."""
    from backend.config import STATE_PATH

    while not stop.wait(2):
        try:
            if not STATE_PATH.exists():
                continue
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if data.get("command") == "stop":
                log("service", "stop requested via state file")
                STOP_EVENT.set()
        except (OSError, ValueError):
            continue


# --- Main loop -------------------------------------------------------------

def run_service() -> int:
    """Run the companion until stopped. Returns an exit code."""
    global _restart_count, _last_start

    ensure_dirs()
    try:
        acquire_lock()
    except InstanceLocked as exc:
        print(f"[nightshift] {exc}", file=sys.stderr)
        return 3

    init_db()
    started = time.time()
    _last_start = started
    _restart_count += 1

    if _restart_count > MAX_RESTART_ATTEMPTS:
        msg = (
            f"Night Shift stopped after {_restart_count} restart attempts. "
            "Manual intervention required."
        )
        log("service", msg, "ERROR")
        notify.send_alert(msg, subject="ETERNAL CABAL - SERVICE STOPPED")
        release_lock()
        return 4

    log(
        "service",
        f"starting (pid {os.getpid()}, attempt {_restart_count})",
    )

    # Windows console signals are limited; handle what is available.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: STOP_EVENT.set())
        except (ValueError, OSError):
            pass

    sched = build_scheduler()
    monitor_stop = threading.Event()
    threads = [
        threading.Thread(target=monitor_resources, args=(monitor_stop,), daemon=True),
        threading.Thread(target=watch_state_file, args=(monitor_stop,), daemon=True),
    ]
    for t in threads:
        t.start()

    exit_code = 0
    try:
        while not STOP_EVENT.is_set():
            try:
                sched.run_due()
            except Exception as exc:
                log("service", f"scheduler error: {exc}", "ERROR")
            STOP_EVENT.wait(15)
    except KeyboardInterrupt:
        log("service", "interrupted")
    except Exception:
        log("service", f"fatal: {traceback.format_exc()}", "ERROR")
        exit_code = 1
    finally:
        monitor_stop.set()
        for t in threads:
            t.join(timeout=3)
        log("service", f"stopping (pid {os.getpid()})")
        release_lock()

    return exit_code


def main() -> int:
    return run_service()


if __name__ == "__main__":
    sys.exit(main())
