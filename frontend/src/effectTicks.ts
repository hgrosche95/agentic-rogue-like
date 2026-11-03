import type { Artifact, Card } from "./api";
import { firingArtifacts } from "./artifactPulse";

// A small number rising off whatever just did something on its own - a
// permanent at the end of the turn (Quarantine's block, a Daemon's hit), an
// artifact at work. Imperative like the card flights: it floats over the
// page, outside React, so a re-render underneath doesn't cut it short.
export type TickTone = "block" | "damage" | "malware" | "heal";

const TICK_MS = 1300;

export function floatTick(el: Element, text: string, tone: TickTone, delay = 0): void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const box = el.getBoundingClientRect();
  if (box.width === 0) return;
  const tick = document.createElement("span");
  tick.className = `effect-tick is-${tone}`;
  tick.textContent = text;
  tick.style.left = `${box.left + box.width / 2}px`;
  tick.style.top = `${box.top + Math.min(box.height / 2, 22)}px`;
  document.body.appendChild(tick);
  const rise = tick.animate(
    [
      { transform: "translate(-50%, 0) scale(0.6)", opacity: 0 },
      { transform: "translate(-50%, -14px) scale(1.12)", opacity: 1, offset: 0.18 },
      { transform: "translate(-50%, -22px) scale(1)", opacity: 1, offset: 0.7 },
      { transform: "translate(-50%, -38px) scale(1)", opacity: 0 },
    ],
    { duration: TICK_MS, delay, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "backwards" },
  );
  rise.onfinish = () => tick.remove();
  rise.oncancel = () => tick.remove();
}

// What a log line says a permanent did: its card type and the tick to show.
const PERMANENT_LINES: [RegExp, Card["type"], TickTone, (m: RegExpMatchArray) => string][] = [
  [/Your quarantine raises (\d+) block/, "quarantine", "block", (m) => `+${m[1]} block`],
  [/Your mainframe raises (\d+) block/, "fortify", "block", (m) => `+${m[1]} block`],
  [/Your daemons hit .* for (\d+) damage/, "turret", "damage", (m) => `${m[1]} dmg`],
  [/Your daemons spread: .*\((\d+)\)/, "turret", "malware", () => "+malware"],
];

// what an artifact's line comes to, as a tick on its chip
function artifactTick(line: string): { text: string; tone: TickTone } | null {
  const m = line.match(/(\d+) (block|damage|Malware|HP)/);
  if (!m) return null;
  const tone: TickTone = m[2] === "block" ? "block" : m[2] === "Malware" ? "malware" : m[2] === "HP" ? "heal" : "damage";
  return { text: `+${m[1]} ${m[2] === "damage" ? "dmg" : m[2].toLowerCase()}`, tone };
}

// The ticks for a batch of new log lines: over the field's permanents (by
// their type) and over the artifacts' chips.
export function showTicks(lines: string[], artifacts: Artifact[]): void {
  let delay = 0;
  for (const line of lines) {
    for (const [re, type, tone, text] of PERMANENT_LINES) {
      const m = line.match(re);
      if (!m) continue;
      document.querySelectorAll(`[data-field-card].type-${type}`).forEach((el) => floatTick(el, text(m), tone, delay));
      delay += 160;
    }
    const firing = firingArtifacts([line], artifacts);
    const tick = firing.length > 0 ? artifactTick(line) : null;
    if (tick) {
      for (const id of firing) {
        const chip = document.querySelector(`[data-artifact-id="${id}"]`);
        if (chip) floatTick(chip, tick.text, tick.tone, delay);
      }
      delay += 160;
    }
  }
}
