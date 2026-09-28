import { useState } from "react";

const RECENT_LINES = 5;

// The run's history as a terminal log: the last few lines, or all of them.
export function HistoryLog({ history }: { history: string[] }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasHistory = history.length > 0;
  const shown = isExpanded ? history : history.slice(-RECENT_LINES);
  const firstNumber = history.length - shown.length + 1;

  return (
    <section className="panel history-log">
      <div className="panel-head">
        <h2 className="panel-title">System log</h2>
        {history.length > RECENT_LINES && (
          <button
            type="button"
            className="link-button"
            aria-expanded={isExpanded}
            onClick={() => setIsExpanded((v) => !v)}
          >
            {isExpanded ? "Show less" : `All ${history.length}`}
          </button>
        )}
      </div>
      <div className={`history-log-lines${isExpanded ? " is-expanded" : ""}`}>
        {hasHistory ? (
          shown.map((line, i) => (
            <p key={firstNumber + i}>
              <span className="log-index">{String(firstNumber + i).padStart(3, "0")}</span>
              {line}
            </p>
          ))
        ) : (
          <p className="muted">Nothing has happened yet.</p>
        )}
      </div>
    </section>
  );
}
