"""Eternal Cabal public site scraper.

Conservative by design: browser User-Agent, long cache TTL, no authentication
bypass, no rate-limit evasion. Only public pages are read.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Optional

import requests

from backend.config import (
    CACHE_TTL_SECONDS,
    HTTP_HEADERS,
    REQUEST_TIMEOUT,
    SITE_PAGES,
)
from backend.db import db, log


class SiteError(Exception):
    """Raised when the site cannot be fetched or parsed."""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:24]


def fetch_page(page_key: str, force: bool = False) -> Optional[str]:
    """Fetch a public page, honouring the cache TTL unless force=True.

    Returns the HTML text, or None when the page is unchanged/unavailable.
    Raises SiteError only on hard failures worth alerting about.
    """
    from backend.config import get_config

    cfg = get_config()
    ttl = int(cfg.get("cache_ttl_seconds", CACHE_TTL_SECONDS))
    url = SITE_PAGES.get(page_key)
    if not url:
        raise SiteError(f"unknown page key: {page_key}")

    if not force:
        with db(readonly=True) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (f"cache:{page_key}",)
            ).fetchone()
        if row:
            try:
                cached = float(row["value"])
                if time.time() - cached < ttl:
                    return None  # still fresh
            except ValueError:
                pass

    try:
        resp = requests.get(
            url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
    except requests.RequestException as exc:
        log("scraper", f"fetch failed for {page_key}: {exc}", "WARNING")
        return None

    if resp.status_code == 403:
        # Cloudflare challenge on the bare domain. Subpages normally pass.
        log("scraper", f"403 challenge on {page_key}", "WARNING")
        return None
    if resp.status_code == 429:
        log("scraper", f"rate limited on {page_key}", "WARNING")
        return None
    if resp.status_code >= 400:
        log("scraper", f"HTTP {resp.status_code} on {page_key}", "WARNING")
        return None

    html = resp.text
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (f"cache:{page_key}", str(time.time())),
        )
    return html


def _text(html: str) -> str:
    """Strip tags and collapse whitespace."""
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#160;", " ")
    return re.sub(r"\s+", " ", t).strip()


def parse_server_info(html: str) -> dict:
    """Extract region, episode, max level and rates from the home page."""
    text = _text(html)
    info: dict = {"raw_hash": _hash(html), "page": "home"}

    m = re.search(r"Region\s+([A-Za-z ]+?)\s+Episode", text)
    info["region"] = m.group(1).strip() if m else None

    m = re.search(r"Episode\s+(\d+)", text)
    info["episode"] = m.group(1) if m else None

    m = re.search(r"Max Lvl\.\s*(\d+)", text)
    info["max_level"] = m.group(1) if m else None

    rates: dict[str, str] = {}
    for label in ("EXP", "Skill Exp", "Pet Exp", "WExp"):
        m = re.search(rf"{re.escape(label)}\.?\s*(\d+x)", text, re.I)
        if m:
            rates[label] = m.group(1)
    info["rates"] = rates
    return info


def parse_download(html: str) -> dict:
    """Extract the newest client version, size and update date."""
    text = _text(html)
    info: dict = {"raw_hash": _hash(html), "page": "download"}

    versions = re.findall(r"Version\s+(\d+)\s+([\d.]+GB)\s+Last Update\s+([\d-]+)", text)
    if versions:
        # First entry is the newest (Mega / Google Drive / MediaFire block).
        v, size, updated = versions[0]
        info["client_version"] = v
        info["client_size"] = size
        info["client_updated"] = updated
    return info


def parse_abusers(html: str, kind: str) -> list[dict]:
    """Parse an abusers leaderboard into rows of character/status/count."""
    text = _text(html)
    rows: list[dict] = []
    pattern = re.compile(
        r"\d+\s+([^\s][^\[]*?)\s+\[(Banned|Suspected|Ban period has ended)\]\s+(\d+)"
    )
    for m in pattern.finditer(text):
        rows.append(
            {
                "character": m.group(1).strip(),
                "status": m.group(2),
                "count": int(m.group(3)),
            }
        )
    return rows


def parse_support_page(html: str, page_key: str) -> dict:
    """Return the readable body of a support page."""
    return {"raw_hash": _hash(html), "page": page_key, "text": _text(html)[:4000]}


def snapshot_server() -> dict:
    """Fetch home + download and store a server snapshot. Returns the snapshot."""
    import json

    home_html = fetch_page("home", force=True)
    dl_html = fetch_page("download", force=True)

    info: dict = {"fetched_at": time.time(), "page": "home"}
    if home_html:
        info.update(parse_server_info(home_html))
    if dl_html:
        info.update(parse_download(dl_html))

    with db() as conn:
        conn.execute(
            "INSERT INTO server_snapshots"
            "(fetched_at, episode, max_level, rates, client_version, client_size,"
            " client_updated, raw_hash, page) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                info["fetched_at"],
                info.get("episode"),
                info.get("max_level"),
                json.dumps(info.get("rates", {})),
                info.get("client_version"),
                info.get("client_size"),
                info.get("client_updated"),
                info.get("raw_hash"),
                info.get("page"),
            ),
        )
    log(
        "scraper",
        f"snapshot: ep={info.get('episode')} rates={info.get('rates')} "
        f"client={info.get('client_version')}",
    )
    return info


def latest_snapshot() -> Optional[dict]:
    import json

    with db(readonly=True) as conn:
        row = conn.execute(
            "SELECT * FROM server_snapshots ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["rates"] = json.loads(d.get("rates") or "{}")
    except ValueError:
        d["rates"] = {}
    return d


def snapshot_changes(prev: Optional[dict], cur: dict) -> list[str]:
    """Describe what changed between two snapshots, for deduped alerts."""
    changes: list[str] = []
    if not prev:
        return ["initial snapshot recorded"]
    for field, label in (
        ("episode", "Episode"),
        ("max_level", "Max level"),
        ("client_version", "Client version"),
        ("client_updated", "Client update date"),
    ):
        if prev.get(field) != cur.get(field) and cur.get(field):
            changes.append(f"{label}: {prev.get(field)} -> {cur.get(field)}")
    prev_rates = prev.get("rates") or {}
    cur_rates = cur.get("rates") or {}
    if prev_rates != cur_rates and cur_rates:
        changes.append(f"Rates: {prev_rates} -> {cur_rates}")
    return changes
