"""Companion health check used by the restart script and the dashboard."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.instance import read_heartbeat  # noqa: E402


def main() -> int:
    hb = read_heartbeat()
    if not hb:
        print("[health] no heartbeat - service is not running")
        return 1

    age = time.time() - float(hb.get("ts", 0))
    if age > 300:
        print(f"[health] STALE - last heartbeat {age:.0f}s ago")
        return 1

    print(f"[health] OK - pid {hb.get('pid')}, heartbeat {age:.0f}s ago")
    extra = hb.get("extra") or {}
    if extra:
        print(f"        rss {extra.get('rss_mb', '?')} MB, cpu {extra.get('cpu_percent', '?')}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
