"""Single-instance lock and heartbeat.

The lock file holds the running PID. A stale lock (process gone) is reclaimed
automatically, so a crash does not block the next start.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from backend.config import HEARTBEAT_PATH, INSTANCE_LOCK_PATH
from backend.db import log


class InstanceLocked(Exception):
    """Raised when another live instance already holds the lock."""


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        # Fallback: signal 0 works on Windows Python for the owning user.
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def acquire_lock(timeout: float = 5.0) -> bool:
    """Take the single-instance lock. Raises InstanceLocked if held live."""
    INSTANCE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(
                str(INSTANCE_LOCK_PATH),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            pid = read_lock_pid()
            if pid is None or not _pid_alive(pid):
                # Stale lock from a dead process: reclaim it.
                try:
                    INSTANCE_LOCK_PATH.unlink()
                    log("instance", f"reclaimed stale lock (pid {pid})")
                except OSError:
                    pass
                if time.time() > deadline:
                    raise InstanceLocked("could not reclaim stale lock")
                time.sleep(0.2)
                continue
            raise InstanceLocked(f"another instance is running (pid {pid})")
        else:
            with os.fdopen(fd, "w") as fh:
                fh.write(str(os.getpid()))
            return True


def read_lock_pid() -> Optional[int]:
    try:
        return int(INSTANCE_LOCK_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def release_lock() -> None:
    """Release the lock if this process owns it."""
    pid = read_lock_pid()
    if pid == os.getpid():
        try:
            INSTANCE_LOCK_PATH.unlink()
        except OSError:
            pass


def write_heartbeat(started_at: float, extra: Optional[dict] = None) -> None:
    """Write the heartbeat file the dashboard reads."""
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "ts": time.time(),
        "started_at": started_at,
        "extra": extra or {},
    }
    tmp = HEARTBEAT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, HEARTBEAT_PATH)


def read_heartbeat() -> Optional[dict]:
    try:
        return json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
