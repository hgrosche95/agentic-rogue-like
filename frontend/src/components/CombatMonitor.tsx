import { useEffect, useState, type ReactNode } from "react";
import { typingInterval, type HackerCommand } from "../hackerCommands";

const VISIBLE_LINES = 4;
const TYPE_INTERVAL_MS = 14;

interface MonitorLine {
  text: string;
  isCommand: boolean;
}

type LineKind = "hit" | "hurt" | "block" | "heal" | "malware" | "banish" | "foe" | "command" | "plain";

// What a history line is about, read from combat.py's wording - for its
// icon and colour. The player's own losses come first: "You block 3 and
// take 5 damage" is a hurt, not a block.
export function lineKind(text: string, isCommand = false): LineKind {
  if (isCommand) return "command";
  if (/You are at \d+ HP|You take \d+|of your HP|cost you \d+ HP/.test(text)) return "hurt";
  if (/banish|uninstall|purges/i.test(text)) return "banish";
  if (/Malware|infect/i.test(text)) return "malware";
  if (
    /^You (play|queue)[^,]*, (dealing|destroying)|hit .* for \d+ damage|goes off for|strike first|backfires|lets the buffer out/.test(
      text,
    )
  )
    return "hit";
  if (/heal|leech|regenerat/i.test(text) && text.startsWith("You")) return "heal";
  if (/block/.test(text) && /^(You|Your)/.test(text)) return "block";
  if (!/^(You|Your|\[)/.test(text)) return "foe";
  return "plain";
}

// Whether the enemy acts in this line - the rounds are split after it.
function enemyActs(text: string): boolean {
  return (
    !/^(You|Your|\[)/.test(text) &&
    /\b(uses |braces itself|charges up|unleashes|releases an overload|strikes|infects you|jams|corrupts)/.test(text)
  );
}

function KindIcon({ kind }: { kind: LineKind }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="monitor-icon">
      {kind === "hit" && <path d="M4 16 15 5M11 4h5v5" />}
      {kind === "hurt" && (
        <>
          <circle cx="10" cy="10" r="7.5" />
          <path d="M10 5.5v5.5M10 14v.5" />
        </>
      )}
      {kind === "block" && <path d="M10 2.6 16 5v4.4c0 4-2.7 6.6-6 8-3.3-1.4-6-4-6-8V5Z" />}
      {kind === "heal" && <path d="M8 3.5h4V8h4.5v4H12v4.5H8V12H3.5V8H8Z" />}
      {kind === "malware" && (
        <>
          <circle cx="10" cy="10" r="3" />
          <path d="M10 2.5v4M10 13.5v4M2.5 10h4M13.5 10h4" />
        </>
      )}
      {kind === "banish" && <path d="M5 5l10 10M15 5 5 15" />}
      {kind === "foe" && (
        <>
          <circle cx="10" cy="11" r="6" />
          <circle cx="10" cy="11" r="1.6" className="fill" />
        </>
      )}
      {kind === "command" && <path d="M4 6l4 4-4 4M10 15h6" />}
      {kind === "plain" && <circle cx="10" cy="10" r="1.6" className="fill" />}
    </svg>
  );
}

// The numbers and names a line is about, in their colours.
const TOKENS =
  /(\d+ (?:\(\+ATK\) )?damage|\d+x \d+ damage|\d+ block|\d+ Malware|Malware \(\d+\)|malware \(\d+\)|\d+ HP)|^(You (?:play|queue|start|uninstall|take) )([^,.-]+?)(?=,| -| in |\.| back| for|$)/g;

function colorize(text: string, kind: LineKind): ReactNode[] {
  if (kind === "command") return [text];
  const out: ReactNode[] = [];
  let at = 0;
  for (const match of text.matchAll(TOKENS)) {
    const start = match.index ?? 0;
    if (start > at) out.push(text.slice(at, start));
    if (match[2] !== undefined) {
      out.push(
        match[2],
        <b key={start} className="tok-card">
          {match[3]}
        </b>,
      );
    } else {
      const token = match[1];
      const tone = /damage/.test(token)
        ? kind === "hurt"
          ? "tok-hurt"
          : "tok-dmg"
        : /block/.test(token)
          ? "tok-block"
          : /alware/.test(token)
            ? "tok-malware"
            : "tok-hp";
      out.push(
        <b key={start} className={tone}>
          {token}
        </b>,
      );
    }
    at = start + match[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

function Line({ line, text, typing, age = 0 }: { line: MonitorLine; text: string; typing?: boolean; age?: number }) {
  const kind = lineKind(line.text, line.isCommand);
  return (
    <p className={`monitor-line is-${kind}${line.isCommand ? " is-command" : ""}${age > 1 ? " is-old" : ""}`}>
      <KindIcon kind={kind} />
      <span>
        {line.isCommand && "$ "}
        {colorize(text, kind)}
        {typing && <span className="monitor-cursor" />}
      </span>
    </p>
  );
}

// Types the line out character by character, like a terminal. Keyed by its
// index in the parent, so a new line remounts it and starts from zero again.
function TypedLine({ line, interval, onDone }: { line: MonitorLine; interval: number; onDone?: () => void }) {
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

  return <Line line={line} text={text.slice(0, shown)} typing={shown < text.length} />;
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
export function CombatMonitor({
  lines,
  commands,
  turn,
}: {
  lines: string[];
  commands: HackerCommand[];
  // the fight's current turn, to number the dividers between the rounds
  turn?: number;
}) {
  // Merged index of the last command that finished typing. The history line
  // a command causes waits for it, so the professor always "hits enter"
  // before the log answers.
  const [typedCommand, setTypedCommand] = useState(-1);
  const merged = mergeLines(lines, commands);
  const visible = merged.slice(-VISIBLE_LINES);
  const firstIndex = merged.length - visible.length;
  const last = merged.length - 1;
  // a divider in front of the first of the player's lines after the enemy
  // acted - numbered back from the current turn
  const splits: number[] = [];
  let acted = false;
  merged.forEach((line, i) => {
    if (!line.isCommand && enemyActs(line.text)) acted = true;
    else if (acted && (line.isCommand || /^(You|Your|\[)/.test(line.text))) {
      splits.push(i);
      acted = false;
    }
  });

  return (
    <div className="arena-monitor">
      <div className="monitor-title">
        <span>Combat log</span>
        <i aria-hidden="true" />
      </div>
      <div className="monitor-lines">
        {visible.map((line, i) => {
          const index = firstIndex + i;
          const split = splits.indexOf(index);
          const divider =
            split >= 0 && i > 0 ? (
              <div key={`turn-${index}`} className="monitor-turn" aria-hidden="true">
                {turn ? `Turn ${turn - (splits.length - 1 - split)}` : "Next turn"}
              </div>
            ) : null;
          return [divider, renderLine(line, index)];
        })}
      </div>
    </div>
  );

  function renderLine(line: MonitorLine, index: number) {
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
    return <Line key={index} line={line} text={line.text} age={last - index} />;
  }
}
