import { useEffect, useState } from "react";
import { typingInterval, type HackerCommand } from "../hackerCommands";

const VISIBLE_LINES = 4;
const TYPE_INTERVAL_MS = 14;

interface MonitorLine {
  text: string;
  isCommand: boolean;
}

function Line({ line, text, typing }: { line: MonitorLine; text: string; typing?: boolean }) {
  return (
    <p className={`monitor-line${line.isCommand ? " is-command" : ""}`}>
      {line.isCommand ? "$" : ">"} {text}
      {typing && <span className="monitor-cursor" />}
    </p>
  );
}

// Types the line out character by character, like a terminal. Keyed by its
// index in the parent, so a new line remounts it and starts from zero again.
function TypedLine({
  line,
  interval,
  onDone,
}: {
  line: MonitorLine;
  interval: number;
  onDone?: () => void;
}) {
  const [shown, setShown] = useState(0);
  const { text } = line;

  useEffect(() => {
    if (shown >= text.length) {
      onDone?.();
      return;
    }
    const timer = setTimeout(() => setShown(shown + 1), interval);
    return () => clearTimeout(timer);
  }, [shown, text, interval, onDone]);

  return <Line line={line} text={text.slice(0, shown)} typing={line.isCommand && shown < text.length} />;
}

// Weaves Dr. Chronos' typed commands in front of the history lines they cause.
function mergeLines(log: string[], commands: HackerCommand[]): MonitorLine[] {
  const merged: MonitorLine[] = [];
  let next = 0;
  log.forEach((text, i) => {
    while (next < commands.length && commands[next].at <= i) {
      merged.push({ text: commands[next++].text, isCommand: true });
    }
    merged.push({ text, isCommand: false });
  });
  for (; next < commands.length; next++) merged.push({ text: commands[next].text, isCommand: true });
  return merged;
}

// The screen hanging over the arena. Its position is baked into the rendered
// background (see .arena-monitor in App.css), so this only fills the glass.
// It shows the run's combat history, with every played card first hacked in
// as a shell command; the encounter agent's own trace is meant to replace
// the history once the API exposes one.
export function CombatMonitor({ lines, commands }: { lines: string[]; commands: HackerCommand[] }) {
  // Merged index of the last command that finished typing. The history line
  // a command causes waits for it, so the professor always "hits enter"
  // before the log answers.
  const [typedCommand, setTypedCommand] = useState(-1);
  const merged = mergeLines(lines, commands);
  const visible = merged.slice(-VISIBLE_LINES);
  const firstIndex = merged.length - visible.length;
  const last = merged.length - 1;

  return (
    <div className="arena-monitor">
      <div className="monitor-title">
        <span>Combat log</span>
        <i aria-hidden="true" />
      </div>
      <div className="monitor-lines">
        {visible.map((line, i) => {
          const index = firstIndex + i;
          if (line.isCommand && index > typedCommand && index >= last - 1) {
            return (
              <TypedLine
                key={index}
                line={line}
                interval={typingInterval(line.text)}
                onDone={() => setTypedCommand((done) => Math.max(done, index))}
              />
            );
          }
          if (index === last) {
            const waiting = index > 0 && merged[index - 1].isCommand && index - 1 > typedCommand;
            return waiting ? null : <TypedLine key={index} line={line} interval={TYPE_INTERVAL_MS} />;
          }
          return <Line key={index} line={line} text={line.text} />;
        })}
      </div>
    </div>
  );
}
