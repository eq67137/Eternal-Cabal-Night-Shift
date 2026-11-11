"""Self-checks for the Night Shift companion.

Run with:  python -m tests.test_all
Exits non-zero if any check fails. Uses a temporary database so it never
touches the real one.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point the database at a temp file BEFORE importing backend modules.
# Use a native Windows path: MSYS /tmp does not resolve for native Python.
_TMP_DB = Path(__file__).resolve().parent / f".test_{os.getpid()}.db"
os.environ["NIGHTSHIFT_TEST_DB"] = str(_TMP_DB)

from backend import analytics, backup, characters, notify, report, scraper  # noqa: E402
from backend.config import DB_PATH  # noqa: E402
from backend.db import db, init_db, log, recent_logs  # noqa: E402
from backend.scheduler import Scheduler  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str):
    """Decorator that runs a test and records the result.

    Returns the original function so it stays callable when collected by name.
    """
    global PASSED, FAILED

    def deco(fn):
        def wrapper():
            global PASSED, FAILED
            try:
                fn()
                PASSED += 1
                print(f"  PASS  {name}")
            except AssertionError as e:
                FAILED += 1
                print(f"  FAIL  {name}: {e}")
            except Exception as e:
                FAILED += 1
                print(f"  ERROR {name}: {type(e).__name__}: {e}")

        wrapper.__name__ = fn.__name__
        wrapper._test_name = name
        return wrapper

    return deco


def setup() -> None:
    """Initialise a clean test database."""
    init_db()


# --- Tests -----------------------------------------------------------------

@check("database schema initialises")
def t_db_init():
    with db(readonly=True) as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for expected in ("characters", "farming_sessions", "market_items",
                     "server_snapshots", "scheduled_jobs", "service_log", "backups"):
        assert expected in tables, f"missing table {expected}"


@check("scheduled jobs are seeded")
def t_jobs_seeded():
    with db(readonly=True) as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM scheduled_jobs").fetchone()["n"]
    assert n >= 6, f"expected >=6 jobs, got {n}"


@check("character create/read/update")
def t_character():
    cid = characters.add_character("TestChar", "Wizard", 42, stats={"str": 10})
    c = characters.get_character(cid)
    assert c["name"] == "TestChar", c
    assert c["level"] == 42, c
    assert c["stats"] == {"str": 10}, c
    characters.update_character(cid, level=43)
    assert characters.get_character(cid)["level"] == 43


@check("farming session math")
def t_farming():
    now = time.time()
    analytics.add_farming_session(
        None, "Ice Witch Town", "NSD", now - 3600, now,
        exp_gained=1200000, items=["Dark Stone"], expenses=5000, revenue=18000,
    )
    s = analytics.farming_summary(days=7)
    assert s["session_count"] == 1, s
    assert abs(s["total_hours"] - 1.0) < 0.01, s
    assert abs(s["exp_per_hour"] - 1200000) < 1, s
    assert s["profit"] == 13000, s


@check("farming summary is zero-safe with no data")
def t_farming_empty():
    s = analytics.farming_summary(days=1, character_id=99999)
    assert s["session_count"] == 0, s
    assert s["exp_per_hour"] == 0.0, s


@check("market price history and change")
def t_market():
    now = time.time()
    analytics.add_market_item("Dark Stone", 1000, recorded_at=now - 86400)
    analytics.add_market_item("Dark Stone", 1200, recorded_at=now)
    ch = analytics.price_change("Dark Stone")
    assert ch is not None, "no change computed"
    assert ch["delta"] == 200, ch
    assert abs(ch["percent"] - 20.0) < 0.01, ch


@check("market report counts tracked items")
def t_market_report():
    rep = analytics.market_report()
    assert rep["tracked_items"] >= 1, rep


@check("daily objectives are idempotent")
def t_objectives():
    cid = characters.add_character("ObjChar", objectives=["Reach level 50", "Craft crest"])
    first = analytics.refresh_daily_objectives(cid)
    second = analytics.refresh_daily_objectives(cid)
    assert len(first) == 2, first
    assert len(second) == 0, f"duplicated: {second}"


@check("objective completion toggles")
def t_objective_complete():
    cid = characters.add_character("DoneChar", objectives=["Task one"])
    analytics.refresh_daily_objectives(cid)
    objs = analytics.list_objectives()
    mine = [o for o in objs if o["character_id"] == cid]
    assert mine, objs
    analytics.complete_objective(mine[0]["id"], True)
    objs = analytics.list_objectives()
    mine = [o for o in objs if o["character_id"] == cid]
    assert mine[0]["done"] == 1, mine


@check("server info parser extracts episode and rates")
def t_parse_server():
    html = (
        "<html><body>Server information Region Asean Episode 39 Max Lvl. 200 "
        "EXP. 8x Skill Exp. 10x Pet Exp. 6x WExp 8x</body></html>"
    )
    info = scraper.parse_server_info(html)
    assert info["episode"] == "39", info
    assert info["max_level"] == "200", info
    assert info["rates"].get("EXP") == "8x", info
    assert info["rates"].get("Skill Exp") == "10x", info


@check("download parser extracts client version")
def t_parse_download():
    html = (
        "<html><body>Mega Version 240 5.4GB Last Update 2026-10-30 Download "
        "Google Drive Version 240 5.4GB Last Update 2026-10-30</body></html>"
    )
    info = scraper.parse_download(html)
    assert info["client_version"] == "240", info
    assert info["client_size"] == "5.4GB", info
    assert info["client_updated"] == "2026-10-30", info


@check("snapshot change detection")
def t_snapshot_changes():
    prev = {"episode": "38", "max_level": "200", "client_version": "230",
            "client_updated": "2026-09-01", "rates": {"EXP": "8x"}}
    cur = {"episode": "39", "max_level": "200", "client_version": "240",
           "client_updated": "2026-10-30", "rates": {"EXP": "8x"}}
    changes = scraper.snapshot_changes(prev, cur)
    assert any("Episode" in c for c in changes), changes
    assert any("Client version" in c for c in changes), changes
    assert not any("Max level" in c for c in changes), changes


@check("snapshot change detection with no previous")
def t_snapshot_changes_first():
    changes = scraper.snapshot_changes(None, {"episode": "39"})
    assert changes == ["initial snapshot recorded"], changes


@check("scheduler computes next run for daily")
def t_sched_daily():
    import datetime

    sched = Scheduler()
    after = datetime.datetime(2026, 11, 11, 5, 0, 0)
    nxt = sched.next_run_after("daily 06:00", after)
    assert (nxt.hour, nxt.minute) == (6, 0), nxt
    assert nxt.day == 11, nxt


@check("scheduler computes next run for interval")
def t_sched_interval():
    import datetime

    sched = Scheduler()
    after = datetime.datetime(2026, 11, 11, 5, 0, 0)
    nxt = sched.next_run_after("every 30 min", after)
    assert (nxt.hour, nxt.minute) == (5, 30), nxt


@check("scheduler due logic")
def t_sched_due():
    sched = Scheduler()
    now = time.time()
    assert sched.due("every 30 min", None, now) is True
    assert sched.due("every 30 min", now - 100, now) is False
    assert sched.due("every 30 min", now - 2000, now) is True


@check("scheduler runs a due job once")
def t_sched_run():
    calls = []

    def job():
        calls.append(1)

    sched = Scheduler()
    sched.register("test_job", "Test", "every 1 min", job)
    ran = sched.run_due()
    assert "test_job" in ran, ran
    assert len(calls) == 1, calls
    # Immediately re-running should not fire again.
    ran2 = sched.run_due()
    assert "test_job" not in ran2, ran2


@check("scheduler records errors without raising")
def t_sched_error():
    def bad():
        raise RuntimeError("boom")

    sched = Scheduler()
    sched.register("bad_job", "Bad", "every 1 min", bad)
    sched.run_due()
    with db(readonly=True) as conn:
        row = conn.execute(
            "SELECT last_status, last_error FROM scheduled_jobs WHERE job_key='bad_job'"
        ).fetchone()
    assert row["last_status"] == "error", row
    assert "boom" in (row["last_error"] or ""), row


@check("notification chunking respects Telegram limit")
def t_notify_chunk():
    # 9000 bytes on one line: the chunker must hard-split it.
    parts = notify._chunk("x" * 9000)
    assert len(parts) > 1, f"expected split, got {len(parts)}"
    for p in parts:
        assert len(p.encode("utf-8")) <= notify.MAX_MESSAGE_BYTES, len(p)
    # Multi-line text splits on line boundaries.
    parts2 = notify._chunk("\n".join(["line"] * 3000))
    assert len(parts2) > 1, len(parts2)
    for p in parts2:
        assert len(p.encode("utf-8")) <= notify.MAX_MESSAGE_BYTES, len(p)
    # Short text stays whole.
    assert notify._chunk("short") == ["short"]


@check("daily report builds without error")
def t_report():
    text = report.build_daily_report()
    assert "ETERNAL CABAL" in text, text[:200]
    assert "Server status:" in text, text[:300]
    assert "Application health:" in text, text[:300]


@check("backup creates and verifies an archive")
def t_backup():
    result = backup.run_backup("test")
    assert result is not None, "backup returned None"
    assert result["verified"] is True, result
    assert Path(result["path"]).exists(), result
    assert len(result["checksum"]) == 64, result


@check("backup verification detects a real archive")
def t_backup_verify():
    result = backup.run_backup("test2")
    with db(readonly=True) as conn:
        bid = conn.execute("SELECT id FROM backups ORDER BY id DESC LIMIT 1").fetchone()["id"]
    assert backup.verify_backup(bid) is True


@check("service log records entries")
def t_log():
    before = len(recent_logs(limit=500))
    log("test", "hello from test")
    after = len(recent_logs(limit=500))
    assert after > before, (before, after)


@check("announcement dedup by hash")
def t_announcement():
    first = report.record_announcement("test", "Title A", "body")
    second = report.record_announcement("test", "Title A", "body")
    assert first is True, first
    assert second is False, second


@check("event dedup by title and start")
def t_event():
    first = report.record_event("Event X", "2026-11-12")
    second = report.record_event("Event X", "2026-11-12")
    assert first is True, first
    assert second is False, second


@check("instance lock is exclusive")
def t_lock():
    from backend import instance

    # Use a dedicated lock path so a running production service cannot
    # interfere with this test.
    import tempfile

    original = instance.INSTANCE_LOCK_PATH
    tmp = Path(__file__).resolve().parent / f".locktest_{os.getpid()}.lock"
    instance.INSTANCE_LOCK_PATH = tmp
    try:
        instance.release_lock()
        assert instance.acquire_lock(timeout=1) is True, "first acquire failed"
        try:
            instance.acquire_lock(timeout=1)
            raise AssertionError("second acquire should have raised")
        except instance.InstanceLocked:
            pass
        instance.release_lock()
        # After release, acquiring again must succeed.
        assert instance.acquire_lock(timeout=1) is True, "re-acquire after release failed"
    finally:
        instance.release_lock()
        instance.INSTANCE_LOCK_PATH = original
        try:
            tmp.unlink()
        except OSError:
            pass


@check("automation policy is disabled by default")
def t_policy():
    from backend.config import AUTOMATION_POLICY

    for key, value in AUTOMATION_POLICY.items():
        assert value is False, f"{key} should be False"


def main() -> int:
    print()
    print("  Eternal Cabal Night Shift - self-checks")
    print(" " + "-" * 46)
    setup()

    tests = [
        t_db_init, t_jobs_seeded, t_character, t_farming, t_farming_empty,
        t_market, t_market_report, t_objectives, t_objective_complete,
        t_parse_server, t_parse_download, t_snapshot_changes,
        t_snapshot_changes_first, t_sched_daily, t_sched_interval,
        t_sched_due, t_sched_run, t_sched_error, t_notify_chunk,
        t_report, t_backup, t_backup_verify, t_log, t_announcement,
        t_event, t_lock, t_policy,
    ]
    for fn in tests:
        fn()

    print(" " + "-" * 46)
    print(f"  {PASSED} passed, {FAILED} failed")
    print()

    try:
        _TMP_DB.unlink(missing_ok=True)
    except OSError:
        pass

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
