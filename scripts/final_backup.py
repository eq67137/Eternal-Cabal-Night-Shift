"""Create a final backup before uninstall, outside the project directory."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import backup  # noqa: E402


def main() -> int:
    dest_dir = Path.home() / "Documents" / "EternalCabalNightShift_final_backup"
    dest_dir.mkdir(parents=True, exist_ok=True)

    result = backup.run_backup("pre_uninstall")
    if not result:
        print("[backup] FAILED - aborting uninstall is recommended")
        return 1

    src = Path(result["path"])
    dest = dest_dir / src.name
    try:
        import shutil

        shutil.copy2(src, dest)
    except OSError as exc:
        print(f"[backup] copy failed: {exc}")
        return 1

    print(f"[backup] final backup: {dest}")
    print(f"[backup] checksum: {result['checksum']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
