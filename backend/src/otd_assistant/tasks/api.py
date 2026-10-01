from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .models import Completion, CompletionRequest, Task, TaskCreate, TaskPatch
from .store import TaskConflict, TaskNotFound, TaskStore


def utc_now() -> datetime:
    return datetime.now(UTC)


def task_router(store: TaskStore) -> APIRouter:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])
    clock = Annotated[datetime, Depends(utc_now)]

    def require_action(action, *args):
        try:
            return action(*args)
        except TaskNotFound as exc:
            raise HTTPException(404, "Task not found") from exc
        except TaskConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("", response_model=Task, status_code=201)
    def create(payload: TaskCreate, now: clock):
        return store.create(payload, now)

    @router.get("", response_model=list[Task])
    def list_tasks(
        now: clock,
        view: Literal["all", "open", "today", "upcoming", "overdue", "completed"] = "open",
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        return store.list_tasks(view, now, limit, offset)

    @router.get("/{task_id}", response_model=Task)
    def get(task_id: UUID):
        return require_action(store.get, str(task_id))

    @router.patch("/{task_id}", response_model=Task)
    def update(task_id: UUID, payload: TaskPatch, now: clock):
        return require_action(store.update, str(task_id), payload, now)

    @router.post("/{task_id}/complete", response_model=Task)
    def complete(task_id: UUID, payload: CompletionRequest, now: clock):
        return require_action(store.complete, str(task_id), payload.expected_updated_at, now)

    @router.get("/{task_id}/completions", response_model=list[Completion])
    def completions(task_id: UUID):
        return require_action(store.completions, str(task_id))

    @router.delete("/{task_id}", status_code=204)
    def delete(task_id: UUID):
        require_action(store.delete, str(task_id))
        return Response(status_code=204)

    return router
