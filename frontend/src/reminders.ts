import { api } from "./api";

interface Reminder {
  id: string; task_id: string; title: string; due_at: string; wake_at: string;
  version: number; presented_at: string | null;
}

export function startReminders(timezone: () => string, onChange: () => Promise<void>): () => Promise<void> {
  const panel = document.getElementById("reminders")!;
  const list = document.getElementById("reminder-list")!;
  const heading = document.getElementById("reminder-title")!;
  const error = document.getElementById("reminder-error")!;
  let polling = false;
  let acting = false;
  let signature = "";

  function fail(value: string): void { error.textContent = value; error.hidden = !value; }
  async function load(): Promise<void> {
    if (polling || acting) return;
    polling = true;
    try {
      const reminders: Reminder[] = [];
      for (let offset = 0; ; offset += 500) {
        const page = await api<Reminder[]>(`/api/reminders?limit=500&offset=${offset}`);
        reminders.push(...page);
        if (page.length < 500) break;
      }
      const status = await api<{running: boolean; error: string | null}>("/api/reminders/status");
      fail(status.error || (!status.running ? "Reminder scheduling is stopped. Restart the service to resume alerts." : ""));
      panel.hidden = reminders.length === 0 && error.hidden;
      heading.textContent = `${reminders.length} reminder${reminders.length === 1 ? " needs" : "s need"} attention`;
      const nextSignature = JSON.stringify(reminders.map(r => [r.id, r.version, r.title, r.wake_at]));
      if (nextSignature !== signature) {
        signature = nextSignature;
        list.replaceChildren();
        for (const reminder of reminders) {
          const row = document.createElement("article"); row.className = "reminder-row";
          const details = document.createElement("div"); details.className = "reminder-details";
          const title = document.createElement("strong"); title.textContent = reminder.title;
          const due = document.createElement("span");
          due.textContent = `Due ${new Intl.DateTimeFormat("en-US", {timeZone: timezone(), month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}).format(new Date(reminder.due_at))}`;
          details.append(title, due); row.append(details);
          for (const [action, label] of [["done", "Done"], ["snooze", "Snooze 10 min"], ["dismiss", "Dismiss"]]) {
            const button = document.createElement("button"); button.textContent = label;
            button.setAttribute("aria-label", `${label}: ${reminder.title}`);
            if (action === "done") button.className = "primary";
            button.addEventListener("click", async () => {
              if (acting) return;
              acting = true;
              list.querySelectorAll("button").forEach(b => b.disabled = true);
              try {
                await api(`/api/reminders/${reminder.id}/action`, "POST", {action, expected_version: reminder.version});
                fail("");
                document.getElementById("assistant-response")!.textContent = action === "done" ? "Task completed." : action === "snooze" ? "I’ll remind you again in 10 minutes." : "Reminder dismissed. Your task remains open.";
                await onChange();
              } catch (cause) {
                fail(cause instanceof Error ? cause.message : "Could not update the reminder.");
                // Keep the error visible until the next poll. Reload retires stale alerts.
                signature = "";
              } finally {
                acting = false;
                list.querySelectorAll("button").forEach(b => b.disabled = false);
              }
              if (error.hidden) await load();
            });
            row.append(button);
          }
          list.append(row);
        }
      }
      const unseen = reminders.filter(r => !r.presented_at).map(r => r.id);
      for (let offset = 0; offset < unseen.length; offset += 500) {
        await api("/api/reminders/presented", "POST", {ids: unseen.slice(offset, offset + 500)});
      }
    } catch (cause) {
      panel.hidden = false;
      fail(cause instanceof Error ? cause.message : "Reminders unavailable. Retrying automatically.");
    } finally { polling = false; }
  }
  document.getElementById("reminder-toggle")!.addEventListener("click", () => {
    list.hidden = !list.hidden;
    document.getElementById("reminder-toggle")!.setAttribute("aria-expanded", String(!list.hidden));
  });
  setInterval(() => { if (!document.hidden) void load(); }, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) void load(); });
  void load();
  return load;
}
