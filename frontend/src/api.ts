export interface Schedule { kind: "once" | "daily" | "weekly"; starts_at: string; timezone: string }
export interface Task {
  id: string; title: string; notes: string; status: "open" | "completed";
  schedule: Schedule | null; next_due_at: string | null; updated_at: string; completed_at: string | null;
}
export interface TaskInput { title: string; notes: string; schedule?: Schedule | null }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method, headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(10000),
    });
  } catch {
    throw new Error(method === "GET" ? "Cannot reach your desk service. Check the connection and refresh." : "The connection was interrupted. Refresh your list before retrying; the change may have been saved.");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === "string" ? error.detail : "Please check the task details and try again.";
    throw new ApiError(response.status, response.status === 409 ? "This task has changed. Close this window and refresh before trying again." : detail);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export async function allTasks(): Promise<Task[]> {
  const tasks: Task[] = [];
  for (let offset = 0; ; offset += 500) {
    const page = await api<Task[]>(`/api/tasks?view=all&limit=500&offset=${offset}`);
    tasks.push(...page);
    if (page.length < 500) return tasks;
  }
}
