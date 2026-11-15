import { useEffect } from "react";
import { sfx } from "../audio";
import type { EventOutcome } from "../eventOutcome";
import { RichText } from "./RichText";

export function EventResult({ outcome, onContinue }: { outcome: EventOutcome; onContinue: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onContinue();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onContinue]);
  const lost = outcome.changes.some((c) => c.tone === "loss");
  const won = outcome.changes.some((c) => c.tone !== "loss");
  return (
    <div className={`event-prompt event-result${won && !lost ? " is-good" : lost && !won ? " is-bad" : ""}`}>
      <span className="event-result-kicker">You chose</span>
      <h2 className="event-result-choice">{outcome.label}</h2>
      <p className="event-result-text">
        <RichText text={outcome.text} />
      </p>
      {outcome.changes.length > 0 && (
        <ul className="event-result-changes" aria-label="What changed">
          {outcome.changes.map((change, i) => (
            <li key={i} className={`event-change is-${change.tone}`} style={{ animationDelay: `${120 + i * 90}ms` }}>
              {change.label}
            </li>
          ))}
        </ul>
      )}
      <button
        className="event-result-continue"
        autoFocus
        onClick={() => {
          sfx.play("click");
          onContinue();
        }}
      >
        Continue
      </button>
    </div>
  );
}
