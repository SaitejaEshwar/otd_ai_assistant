from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from otd_assistant.config import Settings
from otd_assistant.main import create_app
from otd_assistant.tasks.api import utc_now
from otd_assistant.tasks.models import Schedule
from otd_assistant.tasks.scheduling import next_occurrence

NOW = datetime(2026, 10, 1, 17, tzinfo=UTC)


def app_for(path, timezone="America/Chicago"):
    app = create_app(Settings(_env_file=None, database_path=path, timezone=timezone))
    app.dependency_overrides[utc_now] = lambda: NOW
    return app


@pytest.fixture
def client(tmp_path):
    with TestClient(app_for(tmp_path / "tasks.sqlite3")) as client:
        yield client


def create(client, **values):
    response = client.post("/api/tasks", json={"title": "Water plants", **values})
    assert response.status_code == 201, response.text
    return response.json()


def complete(client, task):
    return client.post(f"/api/tasks/{task['id']}/complete", json={"expected_updated_at": task["updated_at"]})


def test_crud_and_completion(client):
    task = create(client, title="  Buy milk  ", notes="Two bottles")
    path = f"/api/tasks/{task['id']}"
    assert task["title"] == "Buy milk"
    assert task["schedule"] is None
    assert client.get(path).json() == task
    assert client.get("/api/tasks").json() == [task]
    task = client.patch(path, json={"title": "Buy oat milk", "notes": ""}).json()
    assert task["notes"] == ""
    done = complete(client, task)
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    assert done.json()["completed_at"] is not None
    assert complete(client, task).json() == done.json()
    assert len(client.get(path + "/completions").json()) == 1
    assert client.get("/api/tasks").json() == []
    assert len(client.get("/api/tasks?view=completed").json()) == 1
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get(path + "/completions").status_code == 404


@pytest.mark.parametrize("kind,expected", [("daily", "2026-10-02T14:00:00Z"), ("weekly", "2026-10-08T14:00:00Z")])
def test_recurring_completion_advances_without_duplicate_retry(client, kind, expected):
    task = create(client, schedule={"kind": kind, "starts_at": "2026-10-01T09:00:00-05:00"})
    assert task["schedule"]["timezone"] == "America/Chicago"
    response = complete(client, task)
    assert response.status_code == 200
    next_task = response.json()
    assert next_task["status"] == "open"
    assert next_task["completed_at"] is None
    assert next_task["next_due_at"] == expected
    assert complete(client, task).status_code == 409
    history = client.get(f"/api/tasks/{task['id']}/completions").json()
    assert len(history) == 1
    assert history[0]["scheduled_for"] == "2026-10-01T14:00:00Z"


def test_one_time_schedule_completion(client):
    task = create(client, schedule={"kind": "once", "starts_at": "2026-10-01T18:00:00Z"})
    done = complete(client, task).json()
    assert done["status"] == "completed"
    assert done["next_due_at"] == task["next_due_at"]
    response = client.patch(f"/api/tasks/{task['id']}", json={"schedule": None})
    assert response.status_code == 409


def test_rescheduling_clearing_and_stale_completion(client):
    task = create(client)
    path = f"/api/tasks/{task['id']}"
    schedule = {"kind": "weekly", "starts_at": "2026-10-02T10:00:00+09:00", "timezone": "Asia/Tokyo"}
    changed = client.patch(path, json={"schedule": schedule})
    assert changed.status_code == 200
    assert changed.json()["next_due_at"] == "2026-10-02T01:00:00Z"
    assert complete(client, task).status_code == 409
    cleared = client.patch(path, json={"schedule": None}).json()
    assert cleared["schedule"] is None
    assert cleared["next_due_at"] is None


def test_views_use_local_calendar_boundaries(client):
    # Chicago day starts at 05:00 UTC and ends at 05:00 UTC the next date.
    previous = create(client, schedule={"kind": "once", "starts_at": "2026-10-01T04:59:59Z"})
    today = create(client, schedule={"kind": "once", "starts_at": "2026-10-01T05:00:00Z"})
    late = create(client, schedule={"kind": "once", "starts_at": "2026-10-02T04:59:59Z"})
    tomorrow = create(client, schedule={"kind": "once", "starts_at": "2026-10-02T05:00:00Z"})
    unscheduled = create(client)
    def ids(view):
        return [task["id"] for task in client.get(f"/api/tasks?view={view}").json()]
    assert ids("today") == [today["id"], late["id"]]
    assert ids("upcoming") == [tomorrow["id"]]
    assert ids("overdue") == [previous["id"], today["id"]]
    assert ids("open")[-1] == unscheduled["id"]
    page = client.get("/api/tasks?limit=2&offset=2").json()
    assert [task["id"] for task in page] == [late["id"], tomorrow["id"]]


@pytest.mark.parametrize("payload", [
    {"title": "   "}, {"title": "x" * 201}, {"title": None},
    {"title": "Task", "notes": "x" * 5001}, {"title": "Task", "status": "completed"},
    {"title": "Task", "schedule": {"kind": "monthly", "starts_at": "2026-10-01T09:00:00Z"}},
    {"title": "Task", "schedule": {"kind": "daily", "starts_at": "2026-10-01T09:00:00"}},
    {"title": "Task", "schedule": {"kind": "daily", "starts_at": "2026-10-01T09:00:00Z", "timezone": "Bad/Zone"}},
])
def test_invalid_create_does_not_write(client, payload):
    assert client.post("/api/tasks", json=payload).status_code == 422
    assert client.get("/api/tasks?view=all").json() == []


@pytest.mark.parametrize("payload", [{}, {"title": None}, {"notes": None}, {"title": " "}, {"status": "completed"}])
def test_invalid_patch_leaves_task_unchanged(client, payload):
    task = create(client)
    path = f"/api/tasks/{task['id']}"
    assert client.patch(path, json=payload).status_code == 422
    assert client.get(path).json() == task


def test_missing_and_invalid_ids_and_query(client):
    path = f"/api/tasks/{uuid4()}"
    assert client.get(path).status_code == 404
    assert client.patch(path, json={"title": "Missing"}).status_code == 404
    assert client.post(path + "/complete", json={"expected_updated_at": NOW.isoformat()}).status_code == 404
    assert client.delete(path).status_code == 404
    assert client.get("/api/tasks/not-a-uuid").status_code == 422
    for query in ("limit=0", "offset=-1", "view=invalid"):
        assert client.get("/api/tasks?" + query).status_code == 422


def test_persistence_across_app_instances(tmp_path):
    path = tmp_path / "nested" / "tasks.sqlite3"
    with TestClient(app_for(path)) as first:
        task = create(first, schedule={"kind": "daily", "starts_at": "2026-10-01T09:00:00-05:00"})
        advanced = complete(first, task).json()
        completed = complete(first, create(first)).json()
    with TestClient(app_for(path)) as restarted:
        assert restarted.get(f"/api/tasks/{task['id']}").json() == advanced
        assert len(restarted.get(f"/api/tasks/{task['id']}/completions").json()) == 1
        assert restarted.get(f"/api/tasks/{completed['id']}").json() == completed


@pytest.mark.parametrize("kind,start,after,expected", [
    ("daily", "2026-03-07T02:30:00-06:00", "2026-03-07T10:00:00Z", "2026-03-08T08:30:00+00:00"),
    ("daily", "2026-03-07T02:30:00-06:00", "2026-03-08T09:00:00Z", "2026-03-09T07:30:00+00:00"),
    ("daily", "2026-10-31T01:30:00-05:00", "2026-10-31T10:00:00Z", "2026-11-01T06:30:00+00:00"),
    ("daily", "2026-10-31T01:30:00-05:00", "2026-11-01T06:30:00Z", "2026-11-02T07:30:00+00:00"),
    ("weekly", "2026-10-25T09:00:00-05:00", "2026-10-25T15:00:00Z", "2026-11-01T15:00:00+00:00"),
    ("weekly", "2026-09-03T09:00:00-05:00", "2026-10-01T17:00:00Z", "2026-10-08T14:00:00+00:00"),
])
def test_recurrence_calendar_and_dst(kind, start, after, expected):
    schedule = Schedule(kind=kind, starts_at=start, timezone="America/Chicago")
    assert next_occurrence(schedule, datetime.fromisoformat(after)).isoformat() == expected


def test_delete_cascades_completion_history(client, tmp_path):
    # Exercise deletion after completion; a fresh connection verifies FK behavior.
    task = create(client)
    complete(client, task)
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    import sqlite3
    with sqlite3.connect(tmp_path / "tasks.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM completions").fetchone()[0] == 0
