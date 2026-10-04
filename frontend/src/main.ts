import "./style.css";
import { startVoice } from "./voice";
import { startReminders } from "./reminders";
import { ApiError, api, allTasks, type Task, type TaskInput, type Schedule } from "./api";

const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const editor = el<HTMLDialogElement>("editor");
const confirmation = el<HTMLDialogElement>("confirmation");
const form = el<HTMLFormElement>("task-form");
const title = el<HTMLInputElement>("title");
const notes = el<HTMLTextAreaElement>("notes");
const repeat = el<HTMLSelectElement>("repeat");
const starts = el<HTMLInputElement>("starts");
const zone = el<HTMLInputElement>("zone");
let tasks: Task[] = [];
let timezone = "America/Chicago";
let view = "today";
let editing: Task | null = null;
let originalSchedule = "";
let pending: (() => Promise<void>) | null = null;
let busy = false;
let refreshing = false;
let loaded = false;
let aiSession: string | null = null;
let aiBusy = false;
interface AssistantReply { session_id: string; kind: "clarification" | "proposal" | "answer" | "saved"; message: string; proposal_id?: string; action?: string; summary?: string[]; }
let returnToEditor = false;
let toastTimer: ReturnType<typeof setTimeout>;

function message(error: unknown): string { return error instanceof Error ? error.message : "Something went wrong. Please try again."; }
function text(tag: string, value: string, className = ""): HTMLElement {
  const node = document.createElement(tag); node.textContent = value; node.className = className; return node;
}
function errorAt(id: string, value = ""): void { el(id).textContent = value; el(id).hidden = !value; }
function notify(value: string): void {
  el("toast").textContent = value; el("toast").hidden = false;
  el("assistant-response").textContent = value;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el("toast").hidden = true; }, 5000);
}
function localDate(value: string | Date, tz = timezone): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(value));
  return ["year", "month", "day"].map(key => parts.find(p => p.type === key)!.value).join("-");
}
function localInput(value: string, tz: string): string {
  const date = new Date(value);
  const time = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
  return `${localDate(date, tz)}T${time}`;
}
function formatDate(value: string, tz = timezone): string {
  return new Intl.DateTimeFormat("en-US", { timeZone: tz, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}
function scheduleText(schedule: Schedule | null | undefined): string {
  if (!schedule) return "No schedule";
  const frequency = { once: "One time", daily: "Every day", weekly: "Every week" }[schedule.kind];
  return `${frequency} · starts ${formatDate(schedule.starts_at, schedule.timezone)} · ${schedule.timezone}`;
}
function tick(): void {
  el("clock").textContent = new Intl.DateTimeFormat("en-US", { timeZone: timezone, weekday: "short", month: "short", day: "numeric" }).format(new Date());
  el("clock").title = timezone;
}
function render(): void {
  const today = localDate(new Date());
  const open = tasks.filter(t => t.status === "open");
  const visible = tasks.filter(task => {
    if (view === "completed") return task.status === "completed";
    if (view === "all") return true;
    if (task.status !== "open") return false;
    if (view === "today") return !task.next_due_at || localDate(task.next_due_at) <= today;
    return !!task.next_due_at && localDate(task.next_due_at) > today;
  });
  const headings: Record<string, string> = { today: "Your focus today", upcoming: "A little further ahead", completed: "Look what you’ve done", all: "Everything on your list" };
  el("list-title").textContent = `${headings[view]} · ${visible.length}`;
  const list = el("task-list"); list.replaceChildren();
  if (!visible.length) {
    const empty = text("div", "", "empty");
    empty.append(text("span", "◌", "empty-mark"), text("h3", view === "completed" ? "Small steps add up." : "A little breathing room."), text("p", view === "completed" ? "Completed tasks will appear here. Repeating tasks advance to their next date." : "Nothing here yet. Add a task whenever you’re ready."));
    list.append(empty);
  }
  for (const task of visible) {
    const row = document.createElement("article"); row.className = "task-row";
    if (task.status === "completed") row.classList.add("is-completed");
    const complete = document.createElement("button"); complete.className = "complete-button";
    complete.textContent = task.status === "completed" ? "✓" : "○";
    complete.setAttribute("aria-label", task.status === "completed" ? `${task.title} is completed` : `Complete ${task.title}`);
    complete.disabled = task.status === "completed";
    complete.addEventListener("click", () => confirmComplete(task));
    const details = document.createElement("button"); details.className = "task-details";
    details.setAttribute("aria-label", `Edit ${task.title}`);
    details.append(text("strong", task.title));
    const overdue = task.status === "open" && !!task.next_due_at && new Date(task.next_due_at) < new Date();
    const detail = task.status === "completed" ? `Completed ${formatDate(task.completed_at!)}` : task.next_due_at ? `${overdue ? "Overdue · " : ""}${formatDate(task.next_due_at)}${task.schedule?.kind !== "once" ? ` · ${task.schedule?.kind}` : ""}` : "Unscheduled";
    details.append(text("span", detail, overdue ? "overdue" : "muted"));
    details.addEventListener("click", () => openEditor(task));
    const remove = document.createElement("button"); remove.className = "delete-button"; remove.textContent = "×";
    remove.setAttribute("aria-label", `Delete ${task.title}`); remove.addEventListener("click", () => confirmDelete(task));
    row.append(complete, details, remove); list.append(row);
  }
  const next = open.filter(t => t.next_due_at && new Date(t.next_due_at) >= new Date()).sort((a, b) => a.next_due_at!.localeCompare(b.next_due_at!))[0];
  el("next-task").textContent = next ? `${next.title} · ${formatDate(next.next_due_at!)}` : "No upcoming times set.";
}
async function refresh(): Promise<void> {
  if (refreshing) return;
  refreshing = true; el<HTMLButtonElement>("refresh").disabled = true;
  try {
    const [health, updated] = await Promise.all([api<{ timezone: string }>("/api/health"), allTasks()]);
    timezone = health.timezone; tasks = updated; loaded = true;
    el("connection").textContent = "● On your device"; errorAt("error"); tick(); render();
  } catch (error) {
    el("connection").textContent = "○ Disconnected"; errorAt("error", message(error));
    if (!loaded) el("task-list").replaceChildren(text("p", "Your tasks will appear when the connection returns.", "empty"));
  } finally { refreshing = false; el<HTMLButtonElement>("refresh").disabled = false; }
}
function scheduleFields(): void {
  const enabled = repeat.value !== "none";
  el("date-field").hidden = !enabled; el("zone-field").hidden = !enabled;
  starts.required = enabled; starts.disabled = !enabled; zone.disabled = !enabled;
}
function signature(): string { return JSON.stringify([repeat.value, starts.value, zone.value]); }
function openEditor(task: Task | null = null, draft = ""): void {
  editing = task; form.reset(); errorAt("form-error");
  title.value = task?.title || draft; notes.value = task?.notes || "";
  repeat.value = task?.schedule?.kind || "none";
  zone.value = task?.schedule?.timezone || timezone;
  starts.value = task?.schedule ? localInput(task.schedule.starts_at, zone.value) : "";
  repeat.disabled = task?.status === "completed";
  scheduleFields(); starts.disabled ||= !!repeat.disabled; zone.disabled ||= !!repeat.disabled;
  originalSchedule = signature();
  el("editor-title").textContent = task ? "Edit task" : "Add a task";
  el("draft-context").hidden = !draft;
  el("draft-context").textContent = `You typed: “${draft}” — I’ll use this as the task title. Choose a schedule below if you need one.`;
  editor.showModal(); title.focus();
}
function openConfirmation(heading: string, lines: string[], label: string, action: () => Promise<void>, fromEditor = false): void {
  returnToEditor = fromEditor; pending = action; errorAt("confirmation-error");
  el("confirmation-title").textContent = heading;
  el("summary").replaceChildren(...lines.map(line => text("p", line)));
  el("confirm").textContent = label; el("confirm").classList.toggle("danger", label === "Delete task");
  el("back").textContent = fromEditor ? "Back to edit" : "Cancel";
  if (editor.open) editor.close(); confirmation.showModal(); el("back").focus();
}
function confirmComplete(task: Task): void {
  openConfirmation("Mark this done?", [task.title, task.schedule && task.schedule.kind !== "once" ? "This occurrence will be recorded as done and the task will move to its next scheduled date." : "This task will move to Completed."], "Mark done", async () => {
    await api(`/api/tasks/${task.id}/complete`, "POST", { expected_updated_at: task.updated_at });
    notify("One more thing done. Nice work.");
  });
}
function confirmDelete(task: Task): void {
  openConfirmation("Delete this task?", [task.title, "This permanently removes the task and its completion history."], "Delete task", async () => {
    await api(`/api/tasks/${task.id}?expected_updated_at=${encodeURIComponent(task.updated_at)}`, "DELETE"); notify("Task deleted.");
  });
}
form.addEventListener("submit", async event => {
  event.preventDefault(); if (busy) return;
  if (!title.value.trim()) { errorAt("form-error", "What would you like to do? Enter a task title."); title.focus(); return; }
  busy = true; el<HTMLButtonElement>("review").disabled = true; errorAt("form-error");
  try {
    const payload: TaskInput = { title: title.value.trim(), notes: notes.value.trim() };
    let schedule = editing?.schedule || null;
    if (!editing || signature() !== originalSchedule) {
      schedule = repeat.value === "none" ? null : await api<Schedule>("/api/schedules/preview", "POST", { kind: repeat.value, local_start: starts.value, timezone: zone.value.trim() });
      payload.schedule = schedule;
    }
    const taskId = editing?.id;
    const taskVersion = editing?.updated_at;
    openConfirmation(taskId ? "Review your changes" : "Ready to add this?", [payload.title, payload.notes, scheduleText(schedule)].filter(Boolean), taskId ? "Save changes" : "Add task", async () => {
      await api(taskId ? `/api/tasks/${taskId}?expected_updated_at=${encodeURIComponent(taskVersion!)}` : "/api/tasks", taskId ? "PATCH" : "POST", payload);
      el<HTMLInputElement>("draft").value = ""; notify(taskId ? "Your task has been updated." : "Added to your list.");
    }, true);
  } catch (error) { errorAt("form-error", message(error)); }
  finally { busy = false; el<HTMLButtonElement>("review").disabled = false; }
});
el("confirm").addEventListener("click", async () => {
  if (busy || !pending) return;
  busy = true; el<HTMLButtonElement>("confirm").disabled = true; el<HTMLButtonElement>("back").disabled = true;
  try { await pending(); returnToEditor = false; confirmation.close(); pending = null; await refresh(); await refreshReminders(); }
  catch (error) { errorAt("confirmation-error", message(error)); }
  finally { busy = false; el<HTMLButtonElement>("confirm").disabled = false; el<HTMLButtonElement>("back").disabled = false; }
});
function cancelConfirmation(): void {
  if (busy) return; confirmation.close(); pending = null;
  if (returnToEditor) { editor.showModal(); title.focus(); }
}
el("back").addEventListener("click", cancelConfirmation);
confirmation.addEventListener("cancel", event => { event.preventDefault(); cancelConfirmation(); });
editor.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
document.querySelectorAll<HTMLButtonElement>("[data-close]").forEach(button => button.addEventListener("click", () => {
  if (busy) return;
  if (button.dataset.close === "confirmation") cancelConfirmation(); else el<HTMLDialogElement>(button.dataset.close!).close();
}));
document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach(button => button.addEventListener("click", () => {
  view = button.dataset.view!;
  document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach(tab => tab.setAttribute("aria-pressed", String(tab === button)));
  render();
}));
el("add").addEventListener("click", () => openEditor());
el("refresh").addEventListener("click", () => void refresh());
repeat.addEventListener("change", scheduleFields);
el("quick-add").addEventListener("submit", async event => {
  event.preventDefault(); const draft = el<HTMLInputElement>("draft").value.trim();
  if (!draft || aiBusy || voiceBusy()) return;
  aiBusy = true; el<HTMLButtonElement>("send").disabled = true; el<HTMLButtonElement>("new-conversation").disabled = true;
  el("send").textContent = "Thinking…"; el("assistant-response").textContent = "Thinking on your device. Your reminders are still running.";
  try {
    const response = await api<AssistantReply>("/api/assistant/chat", "POST", {message: draft, session_id: aiSession}, 100000);
    aiSession = response.session_id; el<HTMLInputElement>("draft").value = "";
    el("assistant-response").textContent = response.message;
    for (const dialog of [editor, confirmation]) {
      if (dialog.open) await new Promise<void>(resolve => dialog.addEventListener("close", () => resolve(), { once: true }));
    }
    if (response.kind === "proposal") {
      openConfirmation("Review your assistant’s proposal", response.summary || [], response.action === "delete" ? "Delete task" : "Confirm", async () => {
        const saved = await api<AssistantReply>("/api/assistant/confirm", "POST", {session_id: aiSession, proposal_id: response.proposal_id});
        notify(saved.message);
      });
    } else {
      el("answer-message").textContent = response.message;
      el<HTMLDialogElement>("assistant-answer").showModal();
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 410) aiSession = null;
    el("assistant-response").textContent = message(error);
    el("answer-message").textContent = message(error);
    el<HTMLDialogElement>("assistant-answer").showModal();
  } finally {
    aiBusy = false; el<HTMLButtonElement>("send").disabled = false; el<HTMLButtonElement>("new-conversation").disabled = false; el("send").textContent = "Send";
    void checkAi();
  }
});
el("new-conversation").addEventListener("click", () => { aiSession = null; notify("New conversation started."); });
el("reply-assistant").addEventListener("click", () => { el<HTMLDialogElement>("assistant-answer").close(); el("draft").focus(); });
async function checkAi(): Promise<void> {
  try { const status = await api<{available:boolean}>("/api/assistant/status"); el("ai-status").textContent = status.available ? "● Local AI ready" : "○ AI offline · Add task still works"; }
  catch { el("ai-status").textContent = "○ AI unavailable · Add task still works"; }
}
const voiceBusy = startVoice(() => aiBusy);

tick(); el("task-list").append(text("p", "Gathering your tasks…", "empty")); void refresh();
const refreshReminders = startReminders(() => timezone, refresh);
void checkAi();
setInterval(() => { tick(); if (!editor.open && !confirmation.open && !document.hidden) void refresh(); }, 60000);
