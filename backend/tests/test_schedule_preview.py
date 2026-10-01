import pytest
from fastapi.testclient import TestClient

from otd_assistant.config import Settings
from otd_assistant.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, database_path=tmp_path / "tasks.sqlite3"))) as client:
        yield client


@pytest.mark.parametrize("zone,local,expected", [
    ("America/Chicago", "2026-10-03T09:00", "2026-10-03T09:00:00-05:00"),
    ("Asia/Kolkata", "2026-10-03T09:00", "2026-10-03T09:00:00+05:30"),
    ("America/Chicago", "2026-11-01T01:30", "2026-11-01T01:30:00-05:00"),
])
def test_preview_uses_selected_zone(client, zone, local, expected):
    response = client.post("/api/schedules/preview", json={"kind": "weekly", "local_start": local, "timezone": zone})
    assert response.status_code == 200
    assert response.json() == {"kind": "weekly", "starts_at": expected, "timezone": zone}
    assert client.get("/api/tasks?view=all").json() == []
    saved = client.post("/api/tasks", json={"title": "From touchscreen", "schedule": response.json()})
    assert saved.status_code == 201
    assert saved.json()["schedule"] == response.json()


@pytest.mark.parametrize("local,zone", [
    ("2026-03-08T02:30", "America/Chicago"),
    ("2026-10-03T09:00Z", "America/Chicago"),
    ("2026-10-03T09:00", "Invalid/Zone"),
    ("not a date", "America/Chicago"),
])
def test_preview_rejects_invalid_or_nonexistent_wall_time(client, local, zone):
    response = client.post("/api/schedules/preview", json={"kind": "once", "local_start": local, "timezone": zone})
    assert response.status_code == 422
