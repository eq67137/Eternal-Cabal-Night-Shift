# Night Shift — Operations Notes

## Windows scheduled task

Task name: `EternalCabalNightShift`

| Setting | Value |
|---|---|
| Trigger | At system startup |
| Delay | 30 seconds |
| Account | Current user, limited privileges |
| Restart | Every 1 minute, for 1 hour |
| Multiple instances | Prevented (single-instance lock) |

Task result codes you may see:

| Code | Meaning |
|---|---|
| `0` | Exited cleanly |
| `0x41301` / `267009` | Task is currently running — normal for a long-lived service |
| `255` | The batch file failed to start Python; check `logs/service.log` |
| `3` | Another instance already holds the lock |

Manage it:

```
python scripts/setup_task.py --status
python scripts/setup_task.py --create
python scripts/setup_task.py --remove
```

## Single-instance protection

`database/companion.lock` holds the running PID. If the process dies, the lock
goes stale and is reclaimed automatically on the next start. You never need to
delete it by hand.

## Heartbeat and state

- `database/heartbeat.json` — written every 60 s by the service. The dashboard
  treats a heartbeat older than 300 s as stale.
- `database/state.json` — carries health data and stop commands between the
  dashboard and the service.

## Logs

`logs/service.log` captures stdout/stderr from the batch file. The database
also holds a structured log (`service_log` table), viewable at
Telegram Reports → Service Log.

## Backup behaviour

- Daily at 05:30, plus a manual button in the dashboard
- Archives in `backups/nightshift_<kind>_<timestamp>.zip`
- Every archive is re-opened and checksum-verified before it is marked verified
- 7-day retention, pruned after each successful backup
- A restore always writes a `pre_restore` backup first

## Crash-loop protection

The service counts its own restarts. After 3 attempts it stops retrying,
writes an ERROR log entry, and sends a Telegram alert asking for manual
intervention. This prevents an uncontrolled restart loop.

## Network and power behaviour

- Site fetch failures are logged as warnings and retried on the next cycle
- A missed run while the PC was asleep executes once on resume
- Telegram outages do not stop the service; the report is recorded as failed
- Sleep and shutdown settings are never modified

## Telegram transport

The companion shells out to `hermes send -t telegram`. This reuses the Hermes
gateway's own credentials, so:

- no bot token is stored in this project
- no second polling process is started
- messages longer than 3900 bytes are split into multiple messages

If the Hermes gateway is not running, `hermes send` still works for
bot-token platforms because it reads the credentials directly.
