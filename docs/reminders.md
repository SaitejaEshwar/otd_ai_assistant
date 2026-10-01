# Reliable reminders

Keep the local service running and the dashboard visible for visual desk alerts. The scheduler checks SQLite once a second; the dashboard checks for alerts every five seconds. Under normal operation an alert appears within about six seconds of its due time. No AI model, internet connection, browser notification permission, or audio device is required.

## Actions

- **Done:** completes a one-time task, or records the current recurring occurrence and advances to its next date. Task completion and reminder acknowledgment commit together.
- **Snooze 10 min:** hides the current alert until ten minutes after the action. The original task due date and recurrence remain unchanged. Snoozes survive service and browser restarts.
- **Dismiss:** acknowledges the current alert without completing the task. One-time tasks remain open/overdue but do not alert again unless rescheduled. Repeating tasks advance to the next date without a completion record.

Repeated scheduler scans do not create duplicate alerts. Each task schedule generation and due occurrence has a unique reminder record. Action requests include the reminder version: a stale retry or a second browser acting on an old copy receives 409, rather than snoozing twice or completing the next occurrence.

Editing a title or notes keeps the same alert. Rescheduling, even to the same date/time, cancels the old reminder and creates a new schedule generation. Completing or deleting a task retires the alert immediately. Daily/weekly recurrence uses the task's saved IANA zone and existing daylight-saving rules.

## Restarts and downtime

At startup, the scheduler reconciles open tasks and recovers due occurrences. Missed alerts appear together in one panel, with one outstanding occurrence per task. It does not generate a burst for every missed day of an unattended repeating task. Done/Dismiss advance a repeating task to the next future occurrence.

SQLite stores snooze times, reminder state, the latest presentation timestamp (reset on snooze), and the latest action timestamp. Pending alerts remain available until acted on, even after they have been displayed. Reloading the browser shows the same outstanding record rather than creating a fresh delivery. Dismissed/done alerts remain suppressed after restart.

When the service or computer is off/asleep, alerts cannot display. Restarting/resuming catches up. With the browser closed, the scheduler continues creating durable pending records; opening the dashboard displays them. Automatic OS startup and Pi kiosk setup remain in the deployment milestone. Visual alert timing relies on the system clock being correct.

## API and diagnostics

| Endpoint | Behavior |
| --- | --- |
| `GET /api/reminders` | Pending reminders whose wake time has arrived; `limit` 1–500 and `offset` support paging. |
| `GET /api/reminders?history=true` | All reminder records, including snoozed, completed, dismissed, and cancelled ones. |
| `POST /api/reminders/presented` | Body `{"ids":["uuid"]}` records first presentation since creation/latest snooze, idempotently. Maximum 500 IDs per request. |
| `POST /api/reminders/{id}/action` | Body `{"action":"snooze","expected_version":0}`; action is `done`, `snooze`, or `dismiss`. Returns the updated record. |
| `GET /api/reminders/status` | Scheduler running state, last successful tick, and recoverable error message. |

The background scheduler runs separately from task HTTP requests and future inference work. Database failures are logged and retried on the next tick; the dashboard reports service/scheduler failures and retries automatically. Shutdown waits for the current database operation to finish.

Schema version 2 automatically migrates the existing version-1 task database transactionally, preserving tasks and completion history. It adds a task schedule generation and reminder records. Unknown future schema versions are rejected. Back up by stopping the service and copying the SQLite file. `OTD_REMINDERS_ENABLED=false` disables background generation for tests/maintenance and is visible as a stopped-scheduler warning.

## Verification

Automated checks cover simultaneous duplicate scans, due-time boundaries, persistent snooze and stale retries, Done/Dismiss semantics, same-time rescheduling, task deletion/completion, missed-occurrence grouping, daylight-saving recurrence, schema migration, and recovery from a scheduler error. Existing task and schedule-preview tests remain enabled. Run `.\.venv\Scripts\python.exe -m pytest -q`.
