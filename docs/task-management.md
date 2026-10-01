# Task management

The local task API and durable storage support the touchscreen dashboard at `http://127.0.0.1:8000/`, including [persistent visual reminders](reminders.md). Use the interactive API documentation at `http://127.0.0.1:8000/docs` or the PowerShell examples below for direct API access.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/tasks` | Create a task (201). |
| GET | `/api/tasks` | List tasks; defaults to open tasks. |
| GET | `/api/tasks/{id}` | Read one task. |
| PATCH | `/api/tasks/{id}` | Change title, notes, or schedule. |
| POST | `/api/tasks/{id}/complete` | Complete a task or its current recurring occurrence. |
| GET | `/api/tasks/{id}/completions` | Read occurrence completion history, newest first. |
| DELETE | `/api/tasks/{id}` | Permanently delete a task and its history (204). |
| POST | `/api/schedules/preview` | Resolve a local date/time in a selected time zone without saving a task. |

Unknown task IDs return 404; invalid requests return 422. Conflicting completion or rescheduling requests return 409. Unexpected input fields are rejected.

Schedule preview accepts `kind`, an offset-free `local_start` (for example `2026-10-03T09:00`), and an IANA `timezone`. It returns a resolved schedule accepted by task creation. Spring-forward nonexistent inputs return 422; fall-back overlaps choose the first occurrence. This differs deliberately from recurring gap handling: the user can clarify an invalid initial wall time, while future recurring occurrences shift as documented below.

## Try a task

Start the application using `scripts/start.ps1`, then run in another PowerShell terminal:

```powershell
$baseUrl = 'http://127.0.0.1:8000/api/tasks'
$body = @{
    title = 'Water the plants'
    notes = 'Check the soil first'
    schedule = @{
        kind = 'weekly'
        starts_at = '2026-10-03T09:00:00-05:00'
        timezone = 'America/Chicago'
    }
} | ConvertTo-Json -Depth 3
$task = Invoke-RestMethod $baseUrl -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod "$baseUrl/$($task.id)"
Invoke-RestMethod "${baseUrl}?view=upcoming"

$changes = @{ notes = 'Check both pots' } | ConvertTo-Json
$task = Invoke-RestMethod "$baseUrl/$($task.id)" -Method Patch -ContentType 'application/json' -Body $changes

$completion = @{ expected_updated_at = $task.updated_at } | ConvertTo-Json
$task = Invoke-RestMethod "$baseUrl/$($task.id)/complete" -Method Post -ContentType 'application/json' -Body $completion
Invoke-RestMethod "$baseUrl/$($task.id)/completions"
```

Use the actual intended date when creating your own tasks. Omit `schedule` for an unscheduled task. Titles are trimmed and must contain 1–200 characters; notes allow up to 5,000. PATCH changes only supplied fields; `{"schedule": null}` removes a schedule, while `{"notes": ""}` clears notes. Explicit null titles/notes and empty patches are rejected. Replacing the schedule resets the current due occurrence to its `starts_at`.

## Schedule and completion rules

- `kind` is `once`, `daily`, or `weekly`. `starts_at` must include a UTC offset or `Z`; offset-free timestamps are rejected. Past starts are allowed and remain overdue until completed, rescheduled, or deleted.
- `timezone` is an IANA zone. When omitted, the task captures `OTD_TIMEZONE` at creation/rescheduling. The start instant is converted to that zone; recurring wall time and weekday are derived from that local value. Changing application configuration does not silently change existing schedules.
- Daily repeats use the same local clock time. Weekly repeats use the same local weekday and clock time. At a spring-forward gap, shift forward by the gap for that occurrence only. At a fall-back overlap, use the first occurrence. The initial occurrence is the explicit `starts_at` instant, including its offset.
- A one-time or unscheduled completion marks the task completed. Repeating tasks stay open and advance to the first occurrence strictly after both the current due instant and completion time. Late completion skips missed dates without inventing completion records for them; early completion advances beyond the occurrence being completed.
- `expected_updated_at` must match the last fetched task when completing an open task. A stale request returns 409 so retries cannot accidentally complete the next recurring occurrence. Reload before deliberately completing again. Completing an already completed one-time task is idempotent.
- Completion history records the original due instant and actual completion time. Title/notes can still be edited after completion; completed tasks cannot be rescheduled. Reopening tasks is outside this milestone.

All audit timestamps and `next_due_at` use UTC. Returned schedules include their time zone and normalized start offset.

## List views

`GET /api/tasks?view=...` supports:

| View | Contents |
| --- | --- |
| `open` | All open tasks, including overdue and unscheduled tasks (default). |
| `all` | Open and completed tasks. |
| `today` | Open tasks due within today's local calendar day. |
| `upcoming` | Open tasks due from the start of tomorrow onward. |
| `overdue` | Open tasks due before the current instant, including earlier today. |
| `completed` | Completed tasks; recurring occurrence history is exposed separately. |

Calendar views use `OTD_TIMEZONE`, even when a task has a different schedule zone. Unscheduled tasks appear in `open`/`all`. Results sort by due instant, with unscheduled tasks last, then creation time and ID for stable pagination. `limit` defaults to 100 (maximum 500); `offset` defaults to zero.

## Storage and recovery

The database is created at application startup. `OTD_DATABASE_PATH` defaults to `data/tasks.sqlite3`, independent of the shell's working directory. The schema stores tasks, schedules, and completion history, with foreign keys and an initial schema version. Unsupported future versions fail startup rather than silently changing data.

Writes use SQLite transactions; completing and advancing a repeating task happens atomically. Connections close after every operation. To back up or transfer data, stop the application, copy the SQLite file, then restart. Both Windows and Pi use the same schema. Keep personal task data out of Git; the default `data/` directory is ignored. If you configure a path elsewhere inside the repository, add that location to `.gitignore`.

The reminder scheduler scans due tasks independently. Completing a task also retires its pending reminder in the same transaction. Replacing/removing a schedule cancels its old alert and starts a new schedule generation; deleting a task removes its reminder history. See [reminder behavior](reminders.md).
