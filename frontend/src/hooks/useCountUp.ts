import { useEffect, useRef, useState } from "react";

function reducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// A number that rolls up to `target` instead of jumping there: from `from`
// (default 0) over `durationMs`, after `delayMs`, easing out so the last
// digits tick slowly - the way a slot machine or Balatro's chips settle.
// With reduced motion it is simply the target.
export function useCountUp(target: number, { from = 0, delayMs = 0, durationMs = 380 } = {}): number {
  const [shown, setShown] = useState(from);
  const start = useRef(from);
  const instant = reducedMotion() || from === target;
  useEffect(() => {
    if (instant) return;
    start.current = from;
    let raf = 0;
    let began = 0;
    const timer = window.setTimeout(() => {
      const tick = (now: number) => {
        if (!began) began = now;
        const k = Math.min(1, (now - began) / durationMs);
        const eased = 1 - Math.pow(1 - k, 3);
        setShown(Math.round(start.current + (target - start.current) * eased));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
  }, [target, from, delayMs, durationMs, instant]);
  return instant ? target : shown;
}
