// How fast a fight plays out: Dr. Chronos typing a card in, the program
// running line by line, hits landing and the enemy's turn. Every combat
// timing goes through tempoMs, so one setting speeds all of them up alike -
// and the pixel scene runs its animations faster by the same factor (see
// PixelStage). Stored like the audio settings (audio/engine.ts).

export type Tempo = "normal" | "fast" | "instant";

export const TEMPOS: { id: Tempo; label: string }[] = [
  { id: "normal", label: "Normal" },
  { id: "fast", label: "Fast" },
  { id: "instant", label: "Instant" },
];

// share of the normal duration each tempo takes
const FACTOR: Record<Tempo, number> = { normal: 1, fast: 0.5, instant: 0.25 };

const TEMPO_KEY = "agentic-rogue-like:tempo";

function loadTempo(): Tempo {
  try {
    const raw = localStorage.getItem(TEMPO_KEY);
    return raw === "fast" || raw === "instant" ? raw : "normal";
  } catch {
    return "normal";
  }
}

let tempo = loadTempo();
const listeners = new Set<() => void>();

export function getTempo(): Tempo {
  return tempo;
}

export function subscribeTempo(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setTempo(next: Tempo) {
  tempo = next;
  try {
    localStorage.setItem(TEMPO_KEY, next);
  } catch {
    // Storage blocked (private mode) - the choice just doesn't survive a reload.
  }
  for (const listener of listeners) listener();
}

// A combat duration at the current tempo.
export function tempoMs(ms: number): number {
  return Math.round(ms * FACTOR[tempo]);
}

// How many times faster than normal the pixel scene plays its animations.
export function tempoSpeed(): number {
  return 1 / FACTOR[tempo];
}
