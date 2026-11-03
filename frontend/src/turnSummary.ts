import type { Artifact, PendingCombatView } from "./api";
import { activeArtifactsLine } from "./artifactTimers";

// What one run of the program came to, shown once it has run: the damage and
// block, the line that did the most, the combos it completed, the lines the
// enemy (or a Segfault) kept from running, and the timed artifacts that
// worked this turn. Read from the preview's steps - what the program was
// played out with.
export interface TurnSummary {
  turn: number;
  dealt: number;
  block: number;
  best: { name: string; dealt: number; runs: number } | null;
  combos: string[];
  lost: number;
  artifacts: string;
}

export function summarizeTurn(combat: PendingCombatView, artifacts: Artifact[]): TurnSummary | null {
  const steps = combat.program_preview?.steps ?? [];
  if (steps.length === 0) return null;
  const ran = steps.filter((s) => s.outcome === "ran");
  const best = ran.reduce<(typeof ran)[number] | null>((top, s) => (s.dealt > (top?.dealt ?? 0) ? s : top), null);
  return {
    turn: combat.turn,
    dealt: ran.reduce((sum, s) => sum + s.dealt, 0),
    block: ran.reduce((sum, s) => sum + s.block, 0),
    best: best ? { name: best.name, dealt: best.dealt, runs: best.runs } : null,
    combos: ran.flatMap((s) => (s.combo ? [s.combo] : [])),
    lost: steps.filter((s) => s.outcome === "cut" || s.outcome === "collected").length,
    artifacts: activeArtifactsLine(artifacts, combat.turn),
  };
}
