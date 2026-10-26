import { API_BASE_URL } from "./api";

// Crashes in the browser are otherwise invisible: the game just freezes on
// the player's screen. Each one goes to the API's log (POST /client-errors)
// with the run it happened in, so it can be found and fixed.

// the run in progress (App keeps it here so a reload can resume it)
export const RUN_ID_KEY = "agentic-rogue-like:run-id";
let sent = 0;
const MAX_REPORTS = 10; // per page load - an error loop must not spam the API

function currentRunId(): string | null {
  try {
    return localStorage.getItem(RUN_ID_KEY);
  } catch {
    return null;
  }
}

export function reportError(where: string, error: unknown, extra = ""): void {
  if (sent >= MAX_REPORTS) return;
  sent++;
  const err = error instanceof Error ? error : new Error(String(error));
  const body = JSON.stringify({
    message: err.message,
    stack: `${err.stack ?? ""}${extra ? `\n${extra}` : ""}`,
    run_id: currentRunId(),
    where,
  });
  // keepalive: the report still goes out if the page is being closed
  fetch(`${API_BASE_URL}/client-errors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {
    // nowhere left to report to
  });
}

export function reportUncaughtErrors(): void {
  window.addEventListener("error", (event) => reportError("window.onerror", event.error ?? event.message));
  window.addEventListener("unhandledrejection", (event) => reportError("unhandledrejection", event.reason));
}
