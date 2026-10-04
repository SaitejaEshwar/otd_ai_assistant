# Touchscreen interface

Open `http://127.0.0.1:8000/` after running `scripts/start.ps1`. Build frontend changes with `pnpm --dir frontend build` and reload the browser. The dashboard targets an 800 × 480 landscape display; buttons are at least 44 × 44 CSS pixels. Narrow displays hide the companion panel to keep task controls usable.

## Everyday controls

- **Today** shows open tasks due today, older overdue tasks, and unscheduled tasks. This intentionally includes more than the API's strict `today` date filter.
- **Upcoming** shows open tasks due tomorrow or later. **Completed** shows completed tasks; repeating tasks stay open and advance to the next date. Completion history remains available through the API.
- **All** includes every task. The application loads all result pages, so the first 100 tasks are not a hidden limit.
- **Add task** opens the title, notes, schedule, and time-zone form. Tap a task title to edit it. Review the exact title and schedule before saving. Use Back to edit or Cancel to discard the pending action.
- Tap the circle to complete a task, or × to delete it. Each action presents a confirmation. Deletion permanently removes the task and its history.
- The bottom input sends a typed request to the local AI. It proposes task changes or asks for clarification; review and confirm before saving. AI status and New conversation remain accessible on narrow screens. See [offline AI setup](offline-ai.md).
- **Talk** starts microphone capture after browser permission. Tap Stop to transcribe locally, or Cancel recording to discard. Review/edit the transcript before Send; task changes still require confirmation. See [voice input](offline-voice.md).

Task times and list dates use the service's configured time zone, not the browser's zone. Existing tasks retain their own recurrence zone. A changed schedule resets the next occurrence; editing only the title/notes preserves it. Completed tasks allow title/notes edits but not rescheduling.

The next scheduled task is informational. Due reminders appear together in a highlighted panel with Done, Snooze 10 min, and Dismiss buttons; the panel can be collapsed without acknowledging its alerts. Reminder state refreshes every five seconds. Refresh reloads the task list, and a one-minute task refresh runs while the page is visible and no dialog is open. The interface shows connection failures and retains drafts after save errors. If a save times out, reload the list before retrying because the server may have saved it already. See [reminder behavior](reminders.md).

## Touch and accessibility

Forms and review dialogs support keyboard navigation, native focus trapping, Escape to cancel, visible focus outlines, and labeled controls. Dialog action buttons remain visible while the body scrolls. Task titles are rendered as text, never HTML. The desktop or Pi OS supplies its on-screen keyboard; kiosk keyboard configuration and physical touch testing remain part of Pi deployment.

## Verification

Backend tests cover schedule conversion in Chicago and Kolkata, the fall-back overlap, nonexistent spring-forward times, invalid zones, and preview-without-saving behavior. Existing task API and persistence tests remain in place.

Manual browser acceptance checks: 800 × 480 dashboard and scrolling form, typed AI request → review → save, recurring completion → Upcoming, notes-only edit preserving the next date, delete confirmation cancellation, and a narrow viewport. Re-run these after interface changes; actual DSI touch hardware is validated on the Pi.
