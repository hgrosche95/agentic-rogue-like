import { useEffect, useState } from "react";

// The server answers with the new HP right away, but the hit that caused it
// is still flying across the arena. Displays follow a value `delayMs` late,
// so bars and numbers change the moment the animation lands.
export const PLAYER_HIT_MS = 350; // the enemy's beam reaching Dr. Chronos
export const ENEMY_HIT_MS = 550; // the pulse down the cable, out of the rift

export function useLagged<T>(value: T, delayMs: number): T {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    if (Object.is(value, shown)) return;
    const timer = window.setTimeout(() => setShown(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, shown, delayMs]);
  return shown;
}
