"""Calendar recurrence calculations, independent of reminder delivery."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Schedule


def normalized_schedule(schedule: Schedule, default_timezone: str) -> Schedule:
    zone = schedule.timezone or default_timezone
    return schedule.model_copy(update={
        "timezone": zone,
        "starts_at": schedule.starts_at.astimezone(ZoneInfo(zone)),
    })


def next_occurrence(schedule: Schedule, after: datetime) -> datetime:
    """Return a recurring occurrence strictly after an aware UTC instant.

    Spring-forward gaps shift forward by the gap; fall-back overlaps choose
    the first occurrence. Recompute from the original wall time each date so
    the spring adjustment never permanently changes the requested time.
    """
    if schedule.kind == "once":
        raise ValueError("One-time schedules have no next occurrence")
    zone = ZoneInfo(schedule.timezone or "UTC")
    anchor = schedule.starts_at.astimezone(zone)
    after = after.astimezone(UTC)
    step = 1 if schedule.kind == "daily" else 7
    days = max(0, (after.astimezone(zone).date() - anchor.date()).days)
    date = anchor.date() + timedelta(days=(days // step) * step)
    while True:
        local = datetime.combine(date, anchor.time().replace(tzinfo=None)).replace(tzinfo=zone, fold=0)
        candidate = local.astimezone(UTC)
        if candidate > after:
            return candidate
        date += timedelta(days=step)
