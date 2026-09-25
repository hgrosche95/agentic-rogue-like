import { useEffect, useState } from "react";

const VISIBLE_LINES = 4;
const TYPE_INTERVAL_MS = 14;

// Types the newest line out character by character, like a terminal. Keyed
// by its history index in the parent, so a new line remounts it and starts
// from zero again.
function TypedLine({ text }: { text: string }) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (shown >= text.length) return;
    const timer = setTimeout(() => setShown(shown + 1), TYPE_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [shown, text]);

  return <p className="monitor-line">&gt; {text.slice(0, shown)}</p>;
}

// The screen hanging over the arena. Its position is baked into the rendered
// background (see .arena-monitor in App.css), so this only fills the glass.
// For now it shows the run's combat history; the encounter agent's own trace
// is meant to replace it once the API exposes one.
export function CombatMonitor({ lines }: { lines: string[] }) {
  const visible = lines.slice(-VISIBLE_LINES);
  const firstIndex = lines.length - visible.length;

  return (
    <div className="arena-monitor">
      <div className="monitor-title">
        <span>Combat log</span>
        <i aria-hidden="true" />
      </div>
      <div className="monitor-lines">
        {visible.map((line, i) => {
          const index = firstIndex + i;
          return index === lines.length - 1 ? (
            <TypedLine key={index} text={line} />
          ) : (
            <p key={index} className="monitor-line">
              &gt; {line}
            </p>
          );
        })}
      </div>
    </div>
  );
}
