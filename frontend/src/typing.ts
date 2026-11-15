import { useEffect, useState } from "react";

// The combat monitor's terminal typing (one character per tick), shared by
// every place that types a line out: the monitor, the system log and the
// AGI's speech bubble. With prefers-reduced-motion the text is there at once.

export const TYPE_INTERVAL_MS = 14;

// The AGI's lines in the run history (combat.CombatVoice, engine): `AGI: "..."`.
export function isAgiLine(text: string): boolean {
  return text.startsWith("AGI:");
}

// The AGI's words without the prefix and the quotes around them.
export function agiWords(text: string): string {
  return text.replace(/^AGI:\s*/, "").replace(/^"(.*)"$/, "$1");
}

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.(REDUCED_MOTION).matches === true,
  );
  useEffect(() => {
    const query = window.matchMedia?.(REDUCED_MOTION);
    if (!query) return;
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

// How many characters of `text` are shown so far. Mount it with a `key` per
// line: a new line starts from zero again. `onDone` fires once it is all out.
export function useTyped(text: string, interval = TYPE_INTERVAL_MS, onDone?: () => void): number {
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(0);
  const visible = reduced ? text.length : shown;

  useEffect(() => {
    if (visible >= text.length) {
      onDone?.();
      return;
    }
    const timer = setTimeout(() => setShown((n) => n + 1), interval);
    return () => clearTimeout(timer);
  }, [visible, text, interval, onDone]);

  return visible;
}
