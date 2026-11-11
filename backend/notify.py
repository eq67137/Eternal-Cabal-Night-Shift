"""Telegram notifications via the existing Hermes gateway.

Uses `hermes send -t telegram`, which reads the gateway's own credentials from
the Hermes config/.env. This project stores no bot token and starts no second
polling process, so it cannot conflict with the running Hermes gateway.
"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

from backend.config import TELEGRAM_TARGET
from backend.db import db, log

# Telegram rejects messages over 4096 bytes; keep a safety margin.
MAX_MESSAGE_BYTES = 3900


class NotifyError(Exception):
    """Raised when a message cannot be delivered."""


def _chunk(text: str, limit: int = MAX_MESSAGE_BYTES) -> list[str]:
    """Split long text into Telegram-safe chunks on line boundaries.

    The limit is a BYTE limit (Telegram counts bytes), so a string of 9000
    ASCII characters must split even though its character count is under 4096.
    """
    if len(text.encode("utf-8")) <= limit:
        return [text]

    out: list[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            out.append(current.rstrip())
        current = ""

    def hard_split(chunk: str) -> str:
        """Emit the leading part of an over-long line, return the remainder."""
        cut = limit
        while cut > 1 and len(chunk[:cut].encode("utf-8")) > limit:
            cut -= 1
        out.append(chunk[:cut])
        return chunk[cut:]

    for line in text.splitlines(keepends=True) or [text]:
        candidate = current + line
        if len(candidate.encode("utf-8")) > limit and current:
            flush()
            current = line
        else:
            current = candidate
        while len(current.encode("utf-8")) > limit:
            current = hard_split(current)

    flush()
    return out or [text[:limit]]


def send_message(
    text: str,
    subject: Optional[str] = None,
    target: Optional[str] = None,
    retries: int = 2,
) -> bool:
    """Send a text message through `hermes send`. Returns True on success.

    Never raises: notification failure is logged and recorded, not propagated,
    so a Telegram outage cannot take down the background companion.
    """
    target = target or TELEGRAM_TARGET
    parts = _chunk(text)
    if subject and len(parts) == 1:
        parts[0] = f"{subject}\n\n{parts[0]}"

    for attempt in range(1, retries + 2):
        ok = True
        for part in parts:
            cmd = ["hermes", "send", "-t", target]
            if subject and len(parts) > 1 and part is parts[0]:
                cmd += ["-s", subject]
            cmd.append(part)
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    shell=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                log("notify", f"send error: {exc}", "ERROR")
                ok = False
                break
            if proc.returncode != 0:
                log(
                    "notify",
                    f"send failed rc={proc.returncode}: {proc.stderr.strip()[:200]}",
                    "ERROR",
                )
                ok = False
                break
        if ok:
            log("notify", f"sent {len(parts)} part(s), {len(text)} chars")
            return True
        if attempt <= retries:
            time.sleep(min(2 ** attempt, 8))

    _record_failure(text)
    return False


def _record_failure(text: str) -> None:
    """Persist a failed notification so it can be retried later."""
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (
                "notify:pending",
                __import__("json").dumps(
                    {
                        "ts": time.time(),
                        "text": text[:1500],
                    }
                ),
            ),
        )


def send_alert(text: str, subject: str = "ETERNAL CABAL ALERT") -> bool:
    """High-priority alert. Same transport, distinct subject line."""
    return send_message(text, subject=subject)


def send_daily_report(report: str) -> bool:
    """Send the scheduled daily report."""
    return send_message(report, subject="ETERNAL CABAL - NIGHT SHIFT REPORT")


def connection_status() -> dict:
    """Check whether the Hermes CLI can reach Telegram (lightweight)."""
    try:
        proc = subprocess.run(
            ["hermes", "send", "--list", "telegram"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        reachable = proc.returncode == 0 and "telegram" in (proc.stdout or "").lower()
        return {
            "reachable": reachable,
            "detail": (proc.stdout or proc.stderr).strip()[:200],
            "checked_at": time.time(),
        }
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"reachable": False, "detail": str(exc)[:200], "checked_at": time.time()}
