import type { EventOptionView, RunView } from "./api";

// What an event did, shown on its own before the map comes back: the choice,
// what came of it (the line the engine wrote into the history), and every
// number that moved as a chip - instead of leaving it to the run log.
export interface EventOutcome {
  label: string;
  text: string;
  changes: { label: string; tone: "gain" | "loss" | "card" }[];
}

const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);

function countNames(names: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);
  return counts;
}

export function eventOutcome(before: RunView, after: RunView, option: EventOptionView): EventOutcome {
  // apply_event_choice writes "> label: outcome"
  const entry = after.history.slice(before.history.length).find((line) => line.startsWith("> "));
  const text = entry?.slice(entry.indexOf(":") + 1).trim() ?? option.effects;
  const was = before.player;
  const now = after.player;
  const changes: EventOutcome["changes"] = [];
  const stat = (label: string, delta: number) => {
    if (delta !== 0) changes.push({ label: `${signed(delta)} ${label}`, tone: delta > 0 ? "gain" : "loss" });
  };
  stat("HP", now.hp - was.hp);
  stat("max HP", now.max_hp - was.max_hp);
  stat("ATK", now.attack - was.attack);
  stat("credits", now.gold - was.gold);
  // cards: what came in and what went, by name
  const had = countNames(was.deck.map((c) => c.name));
  const has = countNames(now.deck.map((c) => c.name));
  for (const [name, n] of has) {
    for (let i = had.get(name) ?? 0; i < n; i++) changes.push({ label: `+ ${name}`, tone: "card" });
  }
  for (const [name, n] of had) {
    for (let i = has.get(name) ?? 0; i < n; i++) changes.push({ label: `− ${name}`, tone: "loss" });
  }
  const known = new Set(was.artifacts.map((a) => a.id));
  for (const artifact of now.artifacts) {
    if (!known.has(artifact.id)) changes.push({ label: `◆ ${artifact.name}`, tone: "gain" });
  }
  return { label: option.label, text, changes };
}
