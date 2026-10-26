import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportError } from "../errors";

// A render error used to unmount the whole app - a frozen, dead screen with
// no way on. Now the error is reported and the player gets a way back in:
// reloading picks the run up again (App keeps its id in localStorage).
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportError("render", error, info.componentStack ?? "");
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="game is-title">
        <div className="end-screen is-lost">
          <h2>Something broke</h2>
          <p>The game hit an error and was reported. Reload - your run picks up where it was.</p>
          <button type="button" className="is-primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </main>
    );
  }
}
