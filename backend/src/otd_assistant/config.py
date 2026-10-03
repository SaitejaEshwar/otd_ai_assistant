from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OTD_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    timezone: str = "America/Chicago"
    database_path: Path = PROJECT_ROOT / "data" / "tasks.sqlite3"
    reminders_enabled: bool = True
    ai_url: str = "http://127.0.0.1:8081"
    ai_model: str = "otd-qwen"
    ai_timeout_seconds: float = Field(default=90, ge=1, le=300)

    @field_validator("ai_url")
    @classmethod
    def local_ai_only(cls, value: str) -> str:
        url = urlsplit(value)
        if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"} or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("AI endpoint must be a local HTTP origin without credentials")
        return value.rstrip("/")

    @field_validator("database_path")
    @classmethod
    def resolve_database_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @field_validator("host")
    @classmethod
    def local_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("The initial version must bind to a loopback address")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA time zone, such as America/Chicago") from exc
        return value
