"""Gracefully stop the running companion service.

Writes a stop command to the state file the service watches, then waits for the
heartbeat to go stale. Falls back to ending the scheduled task.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "database" / "state.json"
HEARTBEAT_PATH = ROOT / "database" / "heartbeat.json"


def main() -> int:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"command": "stop"}), encoding="utf-8")
    print(f"[stop] wrote stop command to {STATE_PATH}")

    # Wait up to 15s for the heartbeat to age out.
    for _ in range(15):
        time.sleep(1)
        try:
            hb = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
            if time.time() - float(hb.get("ts", 0)) > 5:
                print("[stop] service stopped")
                STATE_PATH.write_text(json.dumps({"command": "none"}), encoding="utf-8")
                return 0
        except (OSError, ValueError):
            print("[stop] no heartbeat - service is not running")
            return 0

    print("[stop] service did not stop in time; ending scheduled task")
    subprocess.run(
        ["schtasks", "/End", "/TN", "EternalCabalNightShift"],
        capture_output=True,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
