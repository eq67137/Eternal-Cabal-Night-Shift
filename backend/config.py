"""Central configuration for Eternal Cabal Night Shift.

All paths resolve from the project root so the app works regardless of the
directory it is launched from (scheduled task, dashboard, or manual run).
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is present on the target host
    yaml = None


# --- Paths -----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DATABASE_DIR = ROOT / "database"
SERVER_PROFILES_DIR = ROOT / "server_profiles"
SCHEDULER_DIR = ROOT / "scheduler"
SERVICES_DIR = ROOT / "services"
NOTIFICATIONS_DIR = ROOT / "notifications"
BACKUPS_DIR = ROOT / "backups"
LOGS_DIR = ROOT / "logs"
SCRIPTS_DIR = ROOT / "scripts"
TESTS_DIR = ROOT / "tests"
DOCS_DIR = ROOT / "documentation"

CONFIG_PATH = ROOT / "config.yaml"

# Tests may redirect the database by setting NIGHTSHIFT_TEST_DB before import.
DB_PATH = Path(os.environ.get("NIGHTSHIFT_TEST_DB") or (DATABASE_DIR / "nightshift.db"))
INSTANCE_LOCK_PATH = DATABASE_DIR / "companion.lock"
HEARTBEAT_PATH = DATABASE_DIR / "heartbeat.json"
STATE_PATH = DATABASE_DIR / "state.json"

# --- Timezone --------------------------------------------------------------

TIMEZONE = "Asia/Manila"

# --- Game / site -----------------------------------------------------------

GAME_NAME = "Eternal Cabal SEA"
SITE_BASE = "https://eternal-cabal.com"
SITE_PAGES = {
    "home": f"{SITE_BASE}/home",
    "download": f"{SITE_BASE}/download",
    "abusers_macro": f"{SITE_BASE}/abusers/macro",
    "abusers_dungeon": f"{SITE_BASE}/abusers/dungeon",
    "abusers_nsd": f"{SITE_BASE}/abusers/nsd",
    "abusers_rmt": f"{SITE_BASE}/abusers/rmt",
    "support_guide": f"{SITE_BASE}/support/guide",
    "support_rules": f"{SITE_BASE}/support/rules",
    "support_terms": f"{SITE_BASE}/support/terms",
    "support_contact": f"{SITE_BASE}/support/contact",
}

# Cloudflare challenges the bare domain; subpages serve fine with a browser UA.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 20
CACHE_TTL_SECONDS = 1800          # 30 min between site polls
SERVER_POLL_INTERVAL_MIN = 30     # minutes between server-info checks

# --- Telegram --------------------------------------------------------------
# Reuses the Hermes gateway credentials via `hermes send`. No token is stored
# in this project, so there is no second poller and no credential duplication.
TELEGRAM_TARGET = "telegram"
HERMES_SEND = "hermes"
DAILY_REPORT_HOUR = 6
DAILY_REPORT_MINUTE = 0

# --- Dashboard -------------------------------------------------------------

DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8770

# --- Background service ----------------------------------------------------

HEARTBEAT_INTERVAL_SEC = 60
MAX_RESTART_ATTEMPTS = 3
RESTART_BACKOFF_SEC = 60
MAX_LOG_BYTES = 2_000_000
BACKUP_RETENTION_DAYS = 7

# --- Automation policy (in-game automation is DISABLED by design) -----------

AUTOMATION_POLICY = {
    "auto_combat": False,
    "auto_farming": False,
    "auto_movement": False,
    "auto_dungeon": False,
    "input_simulation": False,
    "packet_manipulation": False,
    "memory_modification": False,
    "dll_injection": False,
    "client_modification": False,
    "anti_cheat_bypass": False,
}


def ensure_dirs() -> None:
    """Create every directory the companion writes to."""
    for d in (
        DATABASE_DIR, SERVER_PROFILES_DIR, SCHEDULER_DIR, SERVICES_DIR,
        NOTIFICATIONS_DIR, BACKUPS_DIR, LOGS_DIR, SCRIPTS_DIR, TESTS_DIR,
        DOCS_DIR, APP_DIR, BACKEND_DIR, FRONTEND_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load config.yaml, returning {} when absent or unparseable."""
    if not CONFIG_PATH.exists() or yaml is None:
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    """Write config.yaml atomically enough for a single-writer local app."""
    if yaml is None:
        return
    tmp = CONFIG_PATH.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)
    os.replace(tmp, CONFIG_PATH)


def get_config() -> dict:
    """Return the merged config (file values override module defaults)."""
    cfg = load_config()
    merged = {
        "timezone": TIMEZONE,
        "site_base": SITE_BASE,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "server_poll_interval_min": SERVER_POLL_INTERVAL_MIN,
        "daily_report_hour": DAILY_REPORT_HOUR,
        "daily_report_minute": DAILY_REPORT_MINUTE,
        "dashboard_host": DASHBOARD_HOST,
        "dashboard_port": DASHBOARD_PORT,
        "backup_retention_days": BACKUP_RETENTION_DAYS,
        "telegram_target": TELEGRAM_TARGET,
        "automation_policy": dict(AUTOMATION_POLICY),
    }
    for key in (
        "timezone", "site_base", "cache_ttl_seconds", "server_poll_interval_min",
        "daily_report_hour", "daily_report_minute", "dashboard_host",
        "dashboard_port", "backup_retention_days", "telegram_target",
    ):
        if key in cfg:
            merged[key] = cfg[key]
    if isinstance(cfg.get("automation_policy"), dict):
        merged["automation_policy"].update(cfg["automation_policy"])
    return merged
