from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from otd_assistant.config import Settings
from otd_assistant.main import create_app


def test_api_and_frontend_coexist(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Desk assistant</h1>", encoding="utf-8")
    client = TestClient(create_app(Settings(_env_file=None), tmp_path))
    assert client.get("/api/health").json() == {
        "status": "ok", "version": "0.1.0", "timezone": "America/Chicago"
    }
    assert "Desk assistant" in client.get("/").text
    assert client.get("/api/missing").status_code == 404


def test_api_works_before_frontend_build(tmp_path):
    client = TestClient(create_app(Settings(_env_file=None), tmp_path))
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 404


@pytest.mark.parametrize("overrides", [{"timezone": "Invalid/Zone"}, {"port": 0}, {"host": "0.0.0.0"}])
def test_invalid_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)
