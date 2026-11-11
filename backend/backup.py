"""Daily backup with integrity verification.

Copies the database plus the YAML config into a timestamped archive. Keeps the
last N daily sets. A backup is only recorded as verified after its checksum is
recomputed from the written file.
"""

from __future__ import annotations

import hashlib
import shutil
import time
import zipfile
from pathlib import Path
from typing import Optional

from backend.config import BACKUP_RETENTION_DAYS, BACKUPS_DIR, CONFIG_PATH, DB_PATH, ROOT
from backend.db import db, log

# Files and directories included in every backup.
BACKUP_ITEMS = [
    DB_PATH,
    CONFIG_PATH,
    ROOT / "server_profiles",
]


def _arcname(path: Path) -> str:
    """Archive path for a backup item.

    The database normally lives under the project root. When it is redirected
    (tests), fall back to a flat name so the archive stays valid.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return f"database/{path.name}"


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_backup(kind: str = "daily") -> Optional[dict]:
    """Create and verify a backup archive. Returns metadata or None on failure."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    archive = BACKUPS_DIR / f"nightshift_{kind}_{stamp}.zip"

    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in BACKUP_ITEMS:
                if not item.exists():
                    continue
                if item.is_file():
                    zf.write(item, arcname=_arcname(item))
                else:
                    for sub in item.rglob("*"):
                        if sub.is_file():
                            zf.write(sub, arcname=_arcname(sub))
    except OSError as exc:
        log("backup", f"backup failed: {exc}", "ERROR")
        return None

    checksum = _checksum(archive)
    size = archive.stat().st_size

    # Verify: reopen and confirm the archive is readable and non-empty.
    verified = False
    try:
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
            verified = bad is None and len(zf.namelist()) > 0
    except zipfile.BadZipFile:
        verified = False

    with db() as conn:
        conn.execute(
            "INSERT INTO backups(created_at, path, size_bytes, checksum, verified, kind)"
            " VALUES(?,?,?,?,?,?)",
            (time.time(), str(archive), size, checksum, 1 if verified else 0, kind),
        )

    log(
        "backup",
        f"backup {archive.name} size={size} verified={verified}",
        "INFO" if verified else "ERROR",
    )

    if verified:
        prune_backups()
    return {
        "path": str(archive),
        "size_bytes": size,
        "checksum": checksum,
        "verified": verified,
    }


def prune_backups(retention_days: Optional[int] = None) -> int:
    """Delete backups older than the retention window. Returns count removed."""
    retention = retention_days or BACKUP_RETENTION_DAYS
    cutoff = time.time() - retention * 86400
    removed = 0
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT id, path FROM backups WHERE created_at < ? ORDER BY created_at",
            (cutoff,),
        ).fetchall()
    for r in rows:
        try:
            Path(r["path"]).unlink(missing_ok=True)
        except OSError:
            pass
        with db() as conn:
            conn.execute("DELETE FROM backups WHERE id=?", (r["id"],))
        removed += 1
    if removed:
        log("backup", f"pruned {removed} backup(s) older than {retention} days")
    return removed


def list_backups() -> list[dict]:
    with db(readonly=True) as conn:
        rows = conn.execute(
            "SELECT * FROM backups ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def verify_backup(backup_id: int) -> bool:
    """Re-verify a stored backup against its recorded checksum."""
    with db(readonly=True) as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        return False
    path = Path(row["path"])
    if not path.exists():
        return False
    actual = _checksum(path)
    ok = actual == row["checksum"]
    with db() as conn:
        conn.execute(
            "UPDATE backups SET verified=? WHERE id=?", (1 if ok else 0, backup_id)
        )
    log("backup", f"verify backup {backup_id}: {'ok' if ok else 'MISMATCH'}",
        "INFO" if ok else "ERROR")
    return ok


def restore_backup(backup_id: int) -> bool:
    """Restore the database from a verified backup.

    The current database is backed up first so a restore is never destructive.
    """
    with db(readonly=True) as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row:
        log("restore", f"backup {backup_id} not found", "ERROR")
        return False
    if not verify_backup(backup_id):
        log("restore", f"backup {backup_id} failed verification", "ERROR")
        return False

    safety = run_backup(kind="pre_restore")
    if not safety:
        log("restore", "refusing restore: safety backup failed", "ERROR")
        return False

    try:
        with zipfile.ZipFile(row["path"]) as zf:
            member = "database/nightshift.db"
            if member not in zf.namelist():
                log("restore", "backup has no database member", "ERROR")
                return False
            tmp = DB_PATH.with_suffix(".restore.tmp")
            with zf.open(member) as src, tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        import os

        os.replace(tmp, DB_PATH)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        log("restore", f"restore failed: {exc}", "ERROR")
        return False

    log("restore", f"restored from {Path(row['path']).name}")
    return True
