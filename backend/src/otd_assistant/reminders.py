"""Persistent reminder lifecycle and an independent, recoverable scheduler."""
import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import logging
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .tasks.api import utc_now
from .tasks.models import InputModel
from .tasks.scheduling import next_occurrence
from .tasks.store import TaskConflict, TaskNotFound, TaskStore, timestamp

logger = logging.getLogger(__name__)


class Reminder(BaseModel):
    id: str
    task_id: str
    title: str
    due_at: datetime
    wake_at: datetime
    state: Literal["pending", "done", "dismissed", "cancelled"]
    version: int
    created_at: datetime
    presented_at: datetime | None
    acted_at: datetime | None


class ReminderAction(InputModel):
    action: Literal["done", "snooze", "dismiss"]
    expected_version: int = Field(ge=0)


class Presented(InputModel):
    ids: list[UUID] = Field(max_length=500)


class ReminderStore:
    def __init__(self, tasks: TaskStore):
        self.tasks = tasks

    @staticmethod
    def reconcile(db, now: datetime) -> None:
        db.execute("""UPDATE reminders SET state = 'cancelled', acted_at = ?
            WHERE state = 'pending' AND NOT EXISTS (
                SELECT 1 FROM tasks t WHERE t.id = reminders.task_id AND t.status = 'open'
                AND t.schedule_version = reminders.schedule_version AND t.next_due_at = reminders.due_at
            )""", (timestamp(now),))

    def tick(self, now: datetime) -> None:
        with self.tasks.connection(write=True) as db:
            self.reconcile(db, now)
            due = db.execute("SELECT id, schedule_version, next_due_at FROM tasks WHERE status = 'open' AND next_due_at <= ?", (timestamp(now),)).fetchall()
            for task in due:
                db.execute("""INSERT OR IGNORE INTO reminders
                    (id,task_id,schedule_version,due_at,wake_at,state,created_at)
                    VALUES (?,?,?,?,?,'pending',?)""", (
                    str(uuid4()), task["id"], task["schedule_version"], task["next_due_at"], task["next_due_at"], timestamp(now),
                ))

    @staticmethod
    def read(db, reminder_id: str) -> Reminder:
        row = db.execute("SELECT r.*, t.title FROM reminders r JOIN tasks t ON t.id = r.task_id WHERE r.id = ?", (reminder_id,)).fetchone()
        if row is None:
            raise TaskNotFound(reminder_id)
        return Reminder.model_validate(dict(row))

    def list_reminders(self, now: datetime, history: bool, limit: int, offset: int) -> list[Reminder]:
        with self.tasks.connection(write=True) as db:
            self.reconcile(db, now)
            where = "1 = 1" if history else "r.state = 'pending' AND r.wake_at <= ?"
            params = () if history else (timestamp(now),)
            rows = db.execute(f"""SELECT r.*,t.title FROM reminders r JOIN tasks t ON t.id = r.task_id
                WHERE {where} ORDER BY r.wake_at, r.id LIMIT ? OFFSET ?""", (*params, limit, offset)).fetchall()
            return [Reminder.model_validate(dict(row)) for row in rows]

    def presented(self, ids: list[UUID], now: datetime) -> None:
        with self.tasks.connection(write=True) as db:
            for reminder_id in ids:
                db.execute("""UPDATE reminders SET presented_at = COALESCE(presented_at, ?)
                    WHERE id = ? AND state = 'pending' AND wake_at <= ?""", (timestamp(now), str(reminder_id), timestamp(now)))

    def act(self, reminder_id: str, payload: ReminderAction, now: datetime) -> Reminder:
        with self.tasks.connection(write=True) as db:
            reminder = self.read(db, reminder_id)
            task = self.tasks.require(db, reminder.task_id)
            generation = db.execute("SELECT schedule_version FROM tasks WHERE id = ?", (task.id,)).fetchone()[0]
            old_generation = db.execute("SELECT schedule_version FROM reminders WHERE id = ?", (reminder_id,)).fetchone()[0]
            if (reminder.state != "pending" or reminder.version != payload.expected_version
                or task.status != "open" or task.next_due_at != reminder.due_at or generation != old_generation):
                raise TaskConflict("This reminder changed. Refresh before acting again.")
            if payload.action == "done":
                self.tasks.complete_in(db, task.id, task.updated_at, now)
            elif payload.action == "dismiss" and task.schedule and task.schedule.kind != "once":
                following = next_occurrence(task.schedule, max(now, reminder.due_at))
                updated = max(now, task.updated_at + timedelta(microseconds=1))
                db.execute("UPDATE tasks SET next_due_at = ?, updated_at = ? WHERE id = ?", (timestamp(following), timestamp(updated), task.id))
            state = {"done": "done", "dismiss": "dismissed", "snooze": "pending"}[payload.action]
            wake = now + timedelta(minutes=10) if payload.action == "snooze" else reminder.wake_at
            db.execute("""UPDATE reminders SET state = ?, wake_at = ?, version = version + 1,
                acted_at = ?, presented_at = CASE WHEN ? = 'snooze' THEN NULL ELSE presented_at END WHERE id = ?""",
                (state, timestamp(wake), timestamp(now), payload.action, reminder_id))
            return self.read(db, reminder_id)


class ReminderScheduler:
    def __init__(self, store: ReminderStore):
        self.store = store
        self.last_tick: datetime | None = None
        self.error: str | None = None
        self.running = False
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.running = True
        try:
            while not self.stop_event.is_set():
                try:
                    now = datetime.now(UTC)
                    await asyncio.to_thread(self.store.tick, now)
                    self.last_tick = now
                    self.error = None
                except Exception:
                    logger.exception("Reminder scheduling failed; retrying on the next tick")
                    self.error = "Reminder scheduling is temporarily unavailable"
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.stop_event.wait(), timeout=1)
        finally:
            self.running = False


def reminder_router(store: ReminderStore, scheduler: ReminderScheduler) -> APIRouter:
    router = APIRouter(prefix="/api/reminders", tags=["reminders"])
    clock = Annotated[datetime, Depends(utc_now)]

    @router.get("", response_model=list[Reminder])
    def list_reminders(now: clock, history: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return store.list_reminders(now, history, limit, offset)

    @router.get("/status")
    def status():
        return {"running": scheduler.running, "last_tick": scheduler.last_tick, "error": scheduler.error}

    @router.post("/presented", status_code=204)
    def presented(payload: Presented, now: clock):
        store.presented(payload.ids, now)

    @router.post("/{reminder_id}/action", response_model=Reminder)
    def action(reminder_id: UUID, payload: ReminderAction, now: clock):
        try:
            return store.act(str(reminder_id), payload, now)
        except TaskNotFound as exc:
            raise HTTPException(404, "Reminder not found") from exc
        except TaskConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
