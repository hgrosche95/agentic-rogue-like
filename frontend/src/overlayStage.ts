import { createContext, useContext } from "react";

// How one window over the screen hands over to the next (see OverlayStage):
// the pick lights up, the window folds shut into a glowing seam while the
// server answers, and the next window opens out of it.

// Which choice of the open window was taken - an option's index, or a name
// for a button like "skip".
export type Pick = number | string;

// open: waiting for a choice. closing: folding shut, the next window (or the
// server's answer) still to come. leaving: folding shut onto the map.
export type StagePhase = "open" | "closing" | "leaving";

export interface OverlayStageState {
  id: string;
  phase: StagePhase;
  picked: Pick | null;
  pick: (choice: Pick) => void;
}

export const OverlayStageContext = createContext<OverlayStageState | null>(null);

// Folding shut takes this long - a beat to confirm the pick, then the
// collapse (.overlay-window.is-closing). Then a short pause before the next
// window opens. Reduced motion keeps only quick fades.
export function stageTimings(): { closeMs: number; beatMs: number; leaveMs: number } {
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return reduced ? { closeMs: 140, beatMs: 0, leaveMs: 140 } : { closeMs: 420, beatMs: 100, leaveMs: 240 };
}

// For a screen inside the stage: report a choice so the window can close
// around it while the request runs. Outside a stage it does nothing.
export function useOverlayPick(): { picked: Pick | null; pick: (choice: Pick) => void } {
  const stage = useContext(OverlayStageContext);
  return { picked: stage?.picked ?? null, pick: stage?.pick ?? (() => {}) };
}

// The class an option gets once something was picked: the pick itself
// flares up, the rest fade back.
export function pickClass(picked: Pick | null, choice: Pick): string {
  if (picked === null) return "";
  return picked === choice ? " is-picked" : " is-passed";
}
