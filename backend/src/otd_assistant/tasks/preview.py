"""Resolve touchscreen wall-clock input without relying on the browser's zone."""
from datetime import UTC
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import NaiveDatetime

from .models import InputModel, Schedule


class SchedulePreview(InputModel):
    kind: Literal["once", "daily", "weekly"]
    local_start: NaiveDatetime
    timezone: str


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.post("/preview", response_model=Schedule)
def preview(payload: SchedulePreview) -> Schedule:
    try:
        zone = ZoneInfo(payload.timezone)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, "Choose a valid IANA time zone") from exc
    local = payload.local_start.replace(tzinfo=zone, fold=0)
    if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != payload.local_start:
        raise HTTPException(422, "This local time does not exist because the clocks move forward. Choose another time.")
    return Schedule(kind=payload.kind, starts_at=local, timezone=payload.timezone)
