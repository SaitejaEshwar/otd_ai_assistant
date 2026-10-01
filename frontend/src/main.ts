import "./style.css";

const status = document.querySelector<HTMLParagraphElement>("#connection")!;
const retry = document.querySelector<HTMLButtonElement>("#retry")!;

async function checkConnection(): Promise<void> {
  retry.disabled = true;
  status.textContent = "Checking the local service…";
  try {
    const response = await fetch("/api/health", { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error("Service unavailable");
    const health: unknown = await response.json();
    if (typeof health !== "object" || health === null || !("status" in health) || health.status !== "ok") {
      throw new Error("Unexpected response");
    }
    status.textContent = "Local service connected. Your workspace is ready.";
  } catch {
    status.textContent = "Cannot reach the local service. Start the backend and try again.";
  } finally {
    retry.disabled = false;
  }
}

retry.addEventListener("click", () => void checkConnection());
void checkConnection();
