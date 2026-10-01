import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from otd_assistant.config import Settings
from otd_assistant.main import create_app
from otd_assistant.reminders import ReminderAction, ReminderScheduler, ReminderStore
from otd_assistant.tasks.api import utc_now
from otd_assistant.tasks.models import Schedule, TaskCreate, TaskPatch
from otd_assistant.tasks.store import TaskConflict, TaskStore, timestamp

NOW = datetime(2026, 10, 1, 17, tzinfo=UTC)


@pytest.fixture
def stores(tmp_path):
    tasks = TaskStore(tmp_path / "tasks.sqlite3", "America/Chicago")
    tasks.initialize()
    return tasks, ReminderStore(tasks)


def task(tasks, kind="once", due=NOW):
    return tasks.create(TaskCreate(title="Reminder test", schedule=Schedule(kind=kind, starts_at=due)), NOW)


def active(reminders, now=NOW):
    return reminders.list_reminders(now, False, 500, 0)


def action(reminders, reminder, kind, now=NOW):
    return reminders.act(reminder.id, ReminderAction(action=kind, expected_version=reminder.version), now)


def test_due_boundaries_and_duplicate_ticks(stores):
    tasks, reminders = stores
    task(tasks)
    task(tasks, due=NOW + timedelta(seconds=1))
    tasks.create(TaskCreate(title="No schedule"), NOW)
    reminders.tick(NOW - timedelta(microseconds=1))
    assert active(reminders) == []
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(reminders.tick, [NOW, NOW]))
    assert len(active(reminders)) == 1
    reminders.tick(NOW + timedelta(seconds=1))
    assert len(active(reminders, NOW + timedelta(seconds=1))) == 2


def test_snooze_persists_and_retry_does_not_extend_it(stores):
    tasks, reminders = stores
    task(tasks)
    reminders.tick(NOW)
    original = active(reminders)[0]
    reminders.presented([UUID(original.id)], NOW)
    assert active(reminders)[0].presented_at == NOW
    snoozed = action(reminders, original, "snooze")
    assert snoozed.wake_at == NOW + timedelta(minutes=10)
    assert snoozed.presented_at is None
    with pytest.raises(TaskConflict):
        action(reminders, original, "snooze", NOW + timedelta(seconds=5))
    restarted_tasks = TaskStore(tasks.path, tasks.timezone)
    restarted_tasks.initialize()
    restarted = ReminderStore(restarted_tasks)
    restarted.tick(NOW + timedelta(minutes=9))
    assert active(restarted, NOW + timedelta(minutes=9)) == []
    restarted.tick(NOW + timedelta(minutes=10))
    assert [r.id for r in active(restarted, NOW + timedelta(minutes=10))] == [original.id]


def test_dismiss_once_leaves_task_open_without_realert(stores):
    tasks, reminders = stores
    created = task(tasks)
    reminders.tick(NOW)
    reminder = active(reminders)[0]
    assert action(reminders, reminder, "dismiss").state == "dismissed"
    assert tasks.get(created.id).status == "open"
    reminders.tick(NOW + timedelta(days=1))
    assert active(reminders, NOW + timedelta(days=1)) == []
    assert len(reminders.list_reminders(NOW, True, 500, 0)) == 1
    assert tasks.completions(created.id) == []


@pytest.mark.parametrize("kind,days", [("daily", 1), ("weekly", 7)])
def test_dismiss_repeat_advances_without_completion(stores, kind, days):
    tasks, reminders = stores
    created = task(tasks, kind)
    reminders.tick(NOW)
    action(reminders, active(reminders)[0], "dismiss")
    updated = tasks.get(created.id)
    assert updated.status == "open"
    assert updated.next_due_at == NOW + timedelta(days=days)
    assert tasks.completions(created.id) == []
    reminders.tick(updated.next_due_at)
    assert len(active(reminders, updated.next_due_at)) == 1


def test_done_is_atomic_and_retry_cannot_complete_next_occurrence(stores):
    tasks, reminders = stores
    created = task(tasks, "daily")
    reminders.tick(NOW)
    old = active(reminders)[0]
    assert action(reminders, old, "done").state == "done"
    with pytest.raises(TaskConflict):
        action(reminders, old, "done")
    assert tasks.get(created.id).next_due_at == NOW + timedelta(days=1)
    assert len(tasks.completions(created.id)) == 1
    assert active(reminders) == []


def test_reschedule_same_due_time_creates_new_generation(stores):
    tasks, reminders = stores
    created = task(tasks)
    reminders.tick(NOW)
    old = active(reminders)[0]
    tasks.update(created.id, TaskPatch(schedule=created.schedule), NOW)
    with pytest.raises(TaskConflict):
        action(reminders, old, "done")
    reminders.tick(NOW)
    assert len(active(reminders)) == 1
    assert active(reminders)[0].id != old.id
    assert reminders.list_reminders(NOW, True, 500, 0)[0].state in ("cancelled", "pending")


@pytest.mark.parametrize("operation", ["complete", "remove_schedule", "delete"])
def test_task_actions_retire_alert(stores, operation):
    tasks, reminders = stores
    created = task(tasks)
    reminders.tick(NOW)
    if operation == "complete":
        tasks.complete(created.id, created.updated_at, NOW)
    elif operation == "remove_schedule":
        tasks.update(created.id, TaskPatch(schedule=None), NOW)
    else:
        tasks.delete(created.id)
    assert active(reminders) == []
    reminders.tick(NOW)
    assert active(reminders) == []


def test_restart_groups_missed_occurrences_without_daily_burst(stores):
    tasks, reminders = stores
    task(tasks, "daily", NOW - timedelta(days=20))
    task(tasks, "weekly", NOW - timedelta(days=30))
    task(tasks, "once", NOW - timedelta(hours=1))
    restarted = ReminderStore(TaskStore(tasks.path, tasks.timezone))
    restarted.tick(NOW)
    assert len(active(restarted)) == 3
    restarted.tick(NOW)
    assert len(active(restarted)) == 3


def test_recurring_reminders_follow_dst(stores):
    tasks, reminders = stores
    start = datetime.fromisoformat("2026-03-07T02:30:00-06:00")
    created = tasks.create(TaskCreate(title="DST", schedule=Schedule(kind="daily", starts_at=start, timezone="America/Chicago")), start)
    reminders.tick(start)
    action(reminders, active(reminders, start)[0], "done", start)
    due = tasks.get(created.id).next_due_at
    assert due == datetime.fromisoformat("2026-03-08T08:30:00+00:00")
    reminders.tick(due - timedelta(seconds=1))
    assert active(reminders, due) == []
    reminders.tick(due)
    assert len(active(reminders, due)) == 1


def test_schema_one_migrates_without_losing_tasks(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,notes TEXT NOT NULL,
            status TEXT NOT NULL,schedule_json TEXT,next_due_at TEXT,created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,completed_at TEXT)""")
        db.execute("INSERT INTO tasks VALUES ('old','Keep me','','open',NULL,NULL,?,?,NULL)", (timestamp(NOW), timestamp(NOW)))
        db.execute("PRAGMA user_version = 1")
    tasks = TaskStore(path, "America/Chicago")
    tasks.initialize()
    tasks.initialize()
    assert tasks.get("old").title == "Keep me"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_reminder_api_validation_and_history(tmp_path):
    path = tmp_path / "api.sqlite3"
    app = create_app(Settings(_env_file=None, database_path=path, reminders_enabled=False))
    app.dependency_overrides[utc_now] = lambda: NOW
    with TestClient(app) as client:
        created = client.post("/api/tasks", json={"title":"API reminder", "schedule":{"kind":"once", "starts_at": NOW.isoformat()}}).json()
        ReminderStore(TaskStore(path, "America/Chicago")).tick(NOW)
        reminder = client.get("/api/reminders").json()[0]
        route = f"/api/reminders/{reminder['id']}/action"
        assert client.post(route, json={"action":"snooze", "expected_version":-1}).status_code == 422
        assert client.post("/api/reminders/presented", json={"ids":[reminder["id"]]}).status_code == 204
        assert client.post(route, json={"action":"done", "expected_version":0}).status_code == 200
        assert client.get(f"/api/tasks/{created['id']}").json()["status"] == "completed"
        assert client.get("/api/reminders").json() == []
        assert client.get("/api/reminders?history=true").json()[0]["presented_at"] is not None
        assert client.post(route, json={"action":"done", "expected_version":0}).status_code == 409


def test_scheduler_recovers_from_failure():
    async def scenario():
        class FakeStore:
            calls = 0
            def tick(self, now):
                self.calls += 1
                if self.calls == 1:
                    raise OSError("temporary database failure")
                loop.call_soon_threadsafe(scheduler.stop_event.set)
        loop = asyncio.get_running_loop()
        store = FakeStore()
        scheduler = ReminderScheduler(store)
        await asyncio.wait_for(scheduler.run(), timeout=5)
        assert store.calls == 2
        assert scheduler.last_tick is not None
        assert scheduler.error is None
        assert scheduler.running is False
    asyncio.run(scenario())


def test_failed_completion_rolls_back_task_and_alert(stores, monkeypatch):
    tasks, reminders = stores
    created = task(tasks, "daily")
    reminders.tick(NOW)
    reminder = active(reminders)[0]
    def broken_recurrence(*args):
        raise RuntimeError("Simulated failure after inserting completion")
    monkeypatch.setattr("otd_assistant.tasks.store.next_occurrence", broken_recurrence)
    with pytest.raises(RuntimeError):
        action(reminders, reminder, "done")
    assert tasks.completions(created.id) == []
    assert tasks.get(created.id) == created
    assert active(reminders)[0].state == "pending"
    assert active(reminders)[0].version == 0
