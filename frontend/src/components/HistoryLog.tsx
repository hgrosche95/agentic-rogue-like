import { useState } from "react";

export function HistoryLog({ history }: { history: string[] }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasHistory = history.length > 0;
  const latestLine = hasHistory ? history[history.length - 1] : "Nothing has happened yet.";

  return (
    <div className="history-log">
      <div className="history-log-row">
        <p className={`history-log-latest${hasHistory ? "" : " muted"}`}>{latestLine}</p>
        {hasHistory && (
          <button
            type="button"
            className="history-log-toggle"
            aria-expanded={isExpanded}
            aria-label={isExpanded ? "Hide log" : "Show full log"}
            onClick={() => setIsExpanded((v) => !v)}
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              {isExpanded ? (
                <>
                  <line x1="3" y1="3" x2="13" y2="13" />
                  <line x1="13" y1="3" x2="3" y2="13" />
                </>
              ) : (
                <>
                  <line x1="2" y1="4" x2="14" y2="4" />
                  <line x1="2" y1="8" x2="14" y2="8" />
                  <line x1="2" y1="12" x2="14" y2="12" />
                </>
              )}
            </svg>
          </button>
        )}
      </div>
      {isExpanded && (
        <div className="history-log-full">
          {history.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </div>
      )}
    </div>
  );
}
