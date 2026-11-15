import { useCallback, useRef } from "react";

// Timed steps of an animation the player may cut short (a click on the arena,
// Space): each step runs at its time - or, skipped, all the ones still to
// come run at once, in order, so the table ends up exactly where it would
// have anyway. A step may queue further steps; a skip runs those at once too.
// `skipping` is true while a skip runs them, for steps to leave out what only
// makes sense in real time (a sound per line, a card's animation).
export function useSequence() {
  const steps = useRef<{ at: number; timer: number; run: () => void }[]>([]);
  const skipping = useRef(false);

  const after = useCallback((ms: number, run: () => void) => {
    // queued by a step that is being skipped: due right away as well
    if (skipping.current) {
      run();
      return;
    }
    const step = { at: performance.now() + ms, timer: 0, run };
    step.timer = window.setTimeout(() => {
      steps.current = steps.current.filter((s) => s !== step);
      run();
    }, ms);
    steps.current.push(step);
  }, []);

  const skip = useCallback((): boolean => {
    if (steps.current.length === 0) return false;
    skipping.current = true;
    try {
      while (steps.current.length > 0) {
        const next = steps.current.reduce((a, b) => (b.at < a.at ? b : a));
        steps.current = steps.current.filter((s) => s !== next);
        window.clearTimeout(next.timer);
        next.run();
      }
    } finally {
      skipping.current = false;
    }
    return true;
  }, []);

  return { after, skip, skipping };
}
