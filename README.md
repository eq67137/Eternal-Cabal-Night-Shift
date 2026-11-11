# Eternal Cabal SEA — Night Shift Companion

An autonomous Windows background companion for Eternal Cabal SEA. It starts with
Windows, monitors public server information, manages character and farming
records, sends Telegram reports, backs up its own data, and recovers from
failures — all without the game client or the dashboard being open.

---

## What it does

| Area | Behaviour |
|---|---|
| Server monitor | Polls the public site every 30 min, caches 30 min, alerts only on real changes |
| Characters | Profiles with class, level, stats, equipment, skills, build, objectives |
| Farming | Sessions with duration, EXP, items, expenses, revenue → EXP/h and profit |
| Dungeons | Locations ranked by recorded EXP/h |
| Market | Price history with change detection |
| Events | Event calendar plus daily objectives |
| Reports | Daily Telegram report at 06:00 Asia/Manila (configurable) |
| Backups | Daily, verified by checksum, 7-day retention |
| Health | Heartbeat, resource watch, error log, dashboard controls |

## What it deliberately does NOT do

In-game automation is **disabled by design** and cannot be enabled from the
dashboard:

- auto-combat, auto-farming, auto-movement, auto-dungeon
- input simulation, packet manipulation, memory modification
- DLL injection, client modification, anti-cheat bypass

The companion reads only public website pages with a normal browser
User-Agent. It does not bypass Cloudflare, authentication, or rate limits.

---

## Requirements

- Windows 10/11
- Python 3.10+ (tested on 3.14)
- Packages: `fastapi`, `uvicorn`, `requests`, `psutil`, `pyyaml`
- A working Hermes Telegram gateway (the companion reuses its credentials
  via `hermes send`; it stores no bot token of its own)

No administrator rights are required. No service wrapper is installed.

---

## Install

Double-click `install.bat`, or from a terminal:

```
install.bat
```

The installer:

1. Locates a Python interpreter with the required packages
2. Installs only genuinely missing packages
3. Initialises `database/nightshift.db`
4. Writes a default `config.yaml`
5. Creates the `EternalCabalNightShift` scheduled task
6. Starts the service and verifies its heartbeat
7. Checks Telegram connectivity
8. Opens the dashboard at <http://127.0.0.1:8770>

## Daily use

| Script | Purpose |
|---|---|
| `start_companion.bat` | Start the background service |
| `stop_companion.bat` | Stop it gracefully |
| `restart_companion.bat` | Stop, then start again |
| `open_dashboard.bat` | Open the dashboard in your browser |
| `uninstall.bat` | Back up, then remove the task and project files |

The service also starts automatically at every Windows startup.

## Dashboard

<http://127.0.0.1:8770> — bound to localhost only, never exposed publicly.

Fourteen pages: Overview, Server Monitor, Character Manager, Build Planner,
Equipment Manager, Farming Analytics, Dungeon Planner, Market Tracker, Event
Calendar, Telegram Reports, Automation Scheduler, Service Health, Backup
Manager, Settings.

The dashboard connects to the running service. Closing it does not stop the
service; opening it does not start a second one.

## Configuration

`config.yaml`:

```yaml
timezone: Asia/Manila
site_base: https://eternal-cabal.com
cache_ttl_seconds: 1800
server_poll_interval_min: 30
daily_report_hour: 6
daily_report_minute: 0
dashboard_host: 127.0.0.1
dashboard_port: 8770
backup_retention_days: 7
telegram_target: telegram
automation_policy:      # all false by design
  auto_combat: false
  auto_farming: false
  auto_movement: false
  auto_dungeon: false
  input_simulation: false
  packet_manipulation: false
  memory_modification: false
  dll_injection: false
  client_modification: false
  anti_cheat_bypass: false
```

## Project layout

```
Eternal-Cabal-Night-Shift/
  backend/         service, dashboard API, scraper, analytics, scheduler
  frontend/        dashboard (HTML/CSS/JS)
  database/        SQLite database, lock, heartbeat
  server_profiles/ per-server saved profiles
  scheduler/       job definitions
  services/        background service helpers
  notifications/   notification channel helpers
  backups/         timestamped, checksum-verified archives
  logs/            service log output
  scripts/         task setup, health check, stop helper
  tests/           self-checks
  documentation/   this file and related notes
```

## Testing

```
python -m tests.test_all
```

27 checks covering the database schema, character and farming math, market
price movement, objective idempotency, site parsers, snapshot change
detection, scheduler timing, notification chunking, report generation, backup
verification, and single-instance locking.

## Troubleshooting

**Dashboard shows "Service stopped"** — start it from Service Health, or run
`start_companion.bat`. Check `logs/service.log`.

**Scheduled task returns 0x41301** — that is normal. It means the task is
currently running.

**Telegram unreachable** — the companion reuses the Hermes gateway. Confirm
`hermes send -t telegram "test"` works.

**Port already in use** — change `dashboard_port` in Settings, or stop
whatever is holding 8770.

## Notes on the game client

The companion never interacts with the game client. It cannot read character
state, so character levels, equipment, farming sessions, and market prices are
entered by you through the dashboard. Reports only ever reflect what was
actually recorded.
