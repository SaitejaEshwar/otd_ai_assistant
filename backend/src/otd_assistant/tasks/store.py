"""SQLite repository. Each operation owns and closes its connection."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

from .models import Completion, Schedule, Task, TaskCreate, TaskPatch
from .scheduling import next_occurrence, normalized_schedule


class TaskNotFound(Exception):
    pass


class TaskConflict(Exception):
    pass


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def task_from_row(row: sqlite3.Row) -> Task:
    values = dict(row)
    values.pop("schedule_version", None)
    values["schedule"] = json.loads(values.pop("schedule_json")) if row["schedule_json"] else None
    return Task.model_validate(values)


class TaskStore:
    def __init__(self, path: Path, timezone: str):
        self.path = path
        self.timezone = timezone

    @contextmanager
    def connection(self, *, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection(write=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError(f"Unsupported task database schema version: {version}")
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('open', 'completed')),
                schedule_json TEXT, next_due_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS completions (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                scheduled_for TEXT, completed_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS tasks_due ON tasks(status, next_due_at)")
            db.execute("CREATE INDEX IF NOT EXISTS completions_task ON completions(task_id, completed_at)")
            if version < 2:
                db.execute("ALTER TABLE tasks ADD COLUMN schedule_version INTEGER NOT NULL DEFAULT 0")
            db.execute("""CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                schedule_version INTEGER NOT NULL, due_at TEXT NOT NULL, wake_at TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','done','dismissed','cancelled')),
                version INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                presented_at TEXT, acted_at TEXT,
                UNIQUE(task_id, schedule_version, due_at)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS reminder_wake ON reminders(state, wake_at)")
            db.execute("PRAGMA user_version = 2")

    @staticmethod
    def require(db: sqlite3.Connection, task_id: str) -> Task:
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFound(task_id)
        return task_from_row(row)

    def get(self, task_id: str) -> Task:
        with self.connection() as db:
            return self.require(db, task_id)

    def create(self, payload: TaskCreate, now: datetime) -> Task:
        schedule = normalized_schedule(payload.schedule, self.timezone) if payload.schedule else None
        task_id = str(uuid4())
        with self.connection(write=True) as db:
            db.execute("INSERT INTO tasks (id,title,notes,status,schedule_json,next_due_at,created_at,updated_at,completed_at) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, NULL)", (
                task_id, payload.title, payload.notes,
                schedule.model_dump_json() if schedule else None,
                timestamp(schedule.starts_at) if schedule else None, timestamp(now), timestamp(now),
            ))
            return self.require(db, task_id)

    def list_tasks(self, view: str, now: datetime, limit: int, offset: int) -> list[Task]:
        local_now = now.astimezone(ZoneInfo(self.timezone))
        start = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=local_now.tzinfo)
        end = start + timedelta(days=1)
        where, params = "1 = 1", []
        if view == "today":
            where, params = "status = 'open' AND next_due_at >= ? AND next_due_at < ?", [timestamp(start), timestamp(end)]
        elif view == "upcoming":
            where, params = "status = 'open' AND next_due_at >= ?", [timestamp(end)]
        elif view == "overdue":
            where, params = "status = 'open' AND next_due_at < ?", [timestamp(now)]
        elif view == "open":
            where = "status = 'open'"
        elif view == "completed":
            where = "status = 'completed'"
        with self.connection() as db:
            rows = db.execute(
                f"SELECT * FROM tasks WHERE {where} ORDER BY next_due_at IS NULL, next_due_at, created_at, id LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            return [task_from_row(row) for row in rows]

    def update(self, task_id: str, payload: TaskPatch, now: datetime, expected_updated_at: datetime | None = None) -> Task:
        with self.connection(write=True) as db:
            task = self.require(db, task_id)
            if expected_updated_at is not None and task.updated_at != expected_updated_at:
                raise TaskConflict("Task changed; review it again before saving")
            schedule = task.schedule
            due = task.next_due_at
            if "schedule" in payload.model_fields_set:
                if task.status == "completed":
                    raise TaskConflict("Cannot reschedule a completed task; create a new task instead")
                schedule = normalized_schedule(payload.schedule, self.timezone) if payload.schedule else None
                due = schedule.starts_at if schedule else None
                db.execute("UPDATE tasks SET schedule_version = schedule_version + 1 WHERE id = ?", (task_id,))
                db.execute("UPDATE reminders SET state = 'cancelled', acted_at = ? WHERE task_id = ? AND state = 'pending'", (timestamp(now), task_id))
            updated = max(now, task.updated_at + timedelta(microseconds=1))
            db.execute("""UPDATE tasks SET title = ?, notes = ?, schedule_json = ?,
                next_due_at = ?, updated_at = ? WHERE id = ?""", (
                payload.title if "title" in payload.model_fields_set else task.title,
                payload.notes if "notes" in payload.model_fields_set else task.notes,
                schedule.model_dump_json() if schedule else None,
                timestamp(due) if due else None, timestamp(updated), task_id,
            ))
            return self.require(db, task_id)

    def complete(self, task_id: str, expected_updated_at: datetime, now: datetime) -> Task:
        with self.connection(write=True) as db:
            return self.complete_in(db, task_id, expected_updated_at, now)

    def complete_in(self, db: sqlite3.Connection, task_id: str, expected_updated_at: datetime, now: datetime) -> Task:
        task = self.require(db, task_id)
        if task.status == "completed":
            return task
        if task.updated_at != expected_updated_at:
            raise TaskConflict("Task changed; reload it before completing")
        due = task.next_due_at
        db.execute("INSERT INTO completions VALUES (?, ?, ?, ?)", (
            str(uuid4()), task_id, timestamp(due) if due else None, timestamp(now),
        ))
        repeating = task.schedule is not None and task.schedule.kind != "once"
        next_due = next_occurrence(task.schedule, max(now, due)) if repeating else due
        updated = max(now, task.updated_at + timedelta(microseconds=1))
        db.execute("""UPDATE tasks SET status = ?, next_due_at = ?, updated_at = ?, completed_at = ?
            WHERE id = ?""", (
            "open" if repeating else "completed", timestamp(next_due) if next_due else None,
            timestamp(updated), None if repeating else timestamp(now), task_id,
        ))
        db.execute("UPDATE reminders SET state = 'done', acted_at = ? WHERE task_id = ? AND state = 'pending'", (timestamp(now), task_id))
        return self.require(db, task_id)

    def completions(self, task_id: str) -> list[Completion]:
        with self.connection() as db:
            self.require(db, task_id)
            return [Completion.model_validate(dict(row)) for row in db.execute(
                "SELECT * FROM completions WHERE task_id = ? ORDER BY completed_at DESC, id", (task_id,)
            )]

    def delete(self, task_id: str, expected_updated_at: datetime | None = None) -> None:
        with self.connection(write=True) as db:
            task = self.require(db, task_id)
            if expected_updated_at is not None and task.updated_at != expected_updated_at:
                raise TaskConflict("Task changed; review it again before deleting")
            db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
