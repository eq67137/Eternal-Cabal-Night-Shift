"""Create, verify, or remove the Windows scheduled task for the companion.

Run directly:  python scripts/setup_task.py --create
               python scripts/setup_task.py --remove
               python scripts/setup_task.py --status

Uses schtasks.exe. No service wrapper, no admin required when the task runs
under the current user account.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK_NAME = "EternalCabalNightShift"
START_SCRIPT = ROOT / "start_companion.bat"


def _run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        args, capture_output=True, text=True, shell=False
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def status() -> bool:
    code, out = _run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"])
    if code != 0:
        print(f"[task] {TASK_NAME} is not registered")
        return False
    print(f"[task] {TASK_NAME} is registered")
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(("Status", "Next Run Time", "TaskName", "Scheduled Task State")):
            print(f"       {line}")
    return True


def create() -> bool:
    if not START_SCRIPT.exists():
        print(f"[task] missing {START_SCRIPT}")
        return False

    # Remove a previous registration so re-running is idempotent.
    _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])

    # /SC ONSTART, 30s delay, current user, limited privileges.
    code, out = _run([
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{START_SCRIPT}"',
        "/SC", "ONSTART",
        "/DELAY", "0000:30",
        "/RU", _username(),
        "/RL", "LIMITED",
        "/F",
    ])
    if code != 0:
        print(f"[task] create failed: {out.strip()[:300]}")
        print("[task] If access is denied, run this script as Administrator once.")
        return False

    # Restart policy: every 1 minute, for 1 hour, and do not start a second
    # instance while one is already running.
    _run(["schtasks", "/Change", "/TN", TASK_NAME, "/RI", "60", "/DU", "0001:00", "/K"])
    _run(["schtasks", "/Change", "/TN", TASK_NAME, "/ENABLE"])

    print(f"[task] created {TASK_NAME}")
    print("       trigger : at system startup, 30s delay")
    print("       restart : every 1 min, max 1 hour")
    print("       account : current user, no admin required")
    return True


def remove() -> bool:
    code, out = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if code != 0:
        print(f"[task] remove failed (may not exist): {out.strip()[:200]}")
        return False
    print(f"[task] removed {TASK_NAME}")
    return True


def _username() -> str:
    import getpass

    return getpass.getuser()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.remove:
        return 0 if remove() else 1
    if args.status:
        return 0 if status() else 1
    if args.create:
        return 0 if create() else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
