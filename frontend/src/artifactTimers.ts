import type { Artifact } from "./api";

// The artifacts that only work every Nth turn (Cache Line, Watchdog Timer,
// Tunnel Vision, Extra RAM, Tail Call): whether this is one of their turns,
// and if not, how many turns until it is - so the HUD can light them up when
// they fire instead of leaving the player to count. Mirrors the backend's
// artifacts.every_nth_turn: active on turns divisible by the interval. The
// extra draw lands as the turn starts; block and Tail Call at its end.

export interface ArtifactTimer {
  active: boolean;
  // turns until the next active one (0: this turn)
  next: number;
  // what it does when active, e.g. "+1 card drawn"
  effect: string;
  tone: "good" | "bad";
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function artifactTimer(artifact: Artifact, turn: number): ArtifactTimer | null {
  const timed = (every: number | undefined, value: number | undefined, effect: string) => {
    if (!value || !every || every <= 1) return null;
    const next = (every - (turn % every)) % every;
    return { active: next === 0, next, effect, tone: value > 0 ? "good" : "bad" } as ArtifactTimer;
  };
  const draw = artifact.extra_draw ?? 0;
  return (
    timed(
      artifact.extra_draw_every,
      draw,
      `${draw > 0 ? "+" : "−"}${plural(Math.abs(draw), "card")} drawn this turn`,
    ) ??
    timed(artifact.turn_block_every, artifact.turn_block, `+${artifact.turn_block} block at the end of the turn`) ??
    timed(artifact.tail_call_every, artifact.tail_call, "the last line runs once more")
  );
}

// A short line for the turn banner: the timed artifacts working this turn.
export function activeArtifactsLine(artifacts: Artifact[], turn: number): string {
  return artifacts
    .flatMap((a) => {
      const timer = artifactTimer(a, turn);
      return timer?.active ? [`${a.name}: ${timer.effect}`] : [];
    })
    .join(" · ");
}
