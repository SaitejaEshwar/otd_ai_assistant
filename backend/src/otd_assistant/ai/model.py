import json
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import Settings


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["create", "update", "complete", "delete", "list", "clarify"]
    target: str | None = Field(description="Existing task title to match, or 'that' for the previous task")
    title: str | None = Field(description="New task title, only for create or rename")
    notes: str | None
    date: str | None = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", description="YYYY-MM-DD local date; null when unspecified")
    time: str | None = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$", description="HH:MM in 24-hour local time; null when unspecified or ambiguous")
    recurrence: Literal["none", "once", "daily", "weekly"] | None
    view: Literal["open", "today", "upcoming", "overdue", "completed", "all"] | None
    question: str | None = Field(description="Short clarification question; never claim an action was executed")

    @field_validator("date", mode="before")
    @classmethod
    def date_only(cls, value):
        # Some small models repeat the time in date despite the output schema.
        # Accept only an ISO datetime, never loosely parse arbitrary prose.
        if isinstance(value, str) and "T" in value:
            from datetime import datetime
            return datetime.fromisoformat(value).date().isoformat()
        return value


class ModelUnavailable(Exception):
    pass


class LanguageModel(Protocol):
    async def interpret(self, messages: list[dict[str, str]]) -> Intent: ...
    async def available(self) -> bool: ...


class LlamaCppModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
                response = await client.get(self.settings.ai_url + "/health")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def interpret(self, messages: list[dict[str, str]]) -> Intent:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=self.settings.ai_timeout_seconds) as client:
                response = await client.post(self.settings.ai_url + "/v1/chat/completions", json={
                    "model": self.settings.ai_model, "messages": messages,
                    "temperature": 0, "max_tokens": 450,
                    "response_format": {"type": "json_schema", "json_schema": {"name": "task_intent", "strict": True, "schema": Intent.model_json_schema()}},
                })
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ValueError("Truncated model response")
                return Intent.model_validate(json.loads(choice["message"]["content"]))
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelUnavailable("The local AI is unavailable or returned an invalid response. Check that the model server is running, or use Add task.") from exc
