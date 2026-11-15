import { useState } from "react";
import { isAgiLine, useTyped } from "../typing";
import { AgiText } from "./AgiText";

const RECENT_LINES = 5;

// One of the AGI's lines as it arrives: typed out like the combat monitor's.
function TypedAgiLine({ text }: { text: string }) {
  const shown = useTyped(text);
  return (
    <>
      <AgiText text={text.slice(0, shown)} />
      {shown < text.length && <span className="monitor-cursor" />}
    </>
  );
}

// The run's history as a terminal log: the last few lines, or all of them.
export function HistoryLog({ history }: { history: string[] }) {
  const [isExpanded, setIsExpanded] = useState(false);
  // Lines already there when the log came up (a resumed run) stand as they are.
  const [firstNew] = useState(history.length);
  const hasHistory = history.length > 0;
  const shown = isExpanded ? history : history.slice(-RECENT_LINES);
  const firstNumber = history.length - shown.length + 1;

  return (
    <section className="panel history-log">
      <div className="panel-head">
        {/* a terminal following the run's log file */}
        <h2 className="panel-title">
          <span className="log-prompt" aria-hidden="true">
            ~/agi $ tail -f{" "}
          </span>
          system.log
        </h2>
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
          shown.map((line, i) => {
            const index = firstNumber + i - 1;
            const agi = isAgiLine(line);
            return (
              <p key={index + 1} className={agi ? "is-agi" : undefined}>
                <span className="log-index">{String(index + 1).padStart(3, "0")}</span>
                {!agi ? line : index >= firstNew ? <TypedAgiLine text={line} /> : <AgiText text={line} />}
              </p>
            );
          })
        ) : (
          <p className="muted">Nothing has happened yet.</p>
        )}
      </div>
    </section>
  );
}
