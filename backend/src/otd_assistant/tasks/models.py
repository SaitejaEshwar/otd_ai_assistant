"""Validated task API contracts. Schedules use explicit instants and IANA zones."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Schedule(InputModel):
    kind: Literal["once", "daily", "weekly"]
    starts_at: AwareDatetime
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("Use a valid IANA time zone") from exc
        return value


class TaskCreate(InputModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=5000)
    schedule: Schedule | None = None


class TaskPatch(InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    schedule: Schedule | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "TaskPatch":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for field in ("title", "notes"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class Task(BaseModel):
    id: str
    title: str
    notes: str
    status: Literal["open", "completed"]
    schedule: Schedule | None
    next_due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class CompletionRequest(InputModel):
    # Optimistic concurrency token also prevents a retried request from completing
    # the *next* occurrence of a repeating task.
    expected_updated_at: AwareDatetime


class Completion(BaseModel):
    id: str
    task_id: str
    scheduled_for: datetime | None
    completed_at: datetime
