import { useCallback, useEffect, useRef, useState } from "react";

// The banners over the arena (components/CombatBanners): what one says and
// how long it stays up, and the queue that plays them one after another.

export type BannerKind = "player" | "enemy" | "phase";

export interface Banner {
  id: number;
  kind: BannerKind;
  title: string;
  sub?: string;
  // how long it stays up, in ms
  ms: number;
}

// A line like `OMEGA: "I predicted you."` split into who says it and what.
export function splitTaunt(taunt: string): { speaker: string | null; line: string } {
  const match = /^([^:"]{1,40}):\s*"(.*)"$/.exec(taunt.trim());
  return match ? { speaker: match[1], line: match[2] } : { speaker: null, line: taunt.trim() };
}

// Banners play one after another - an enemy's turn, its overclock and the
// player's next turn can all come out of one answer from the server. `show`
// queues one, `delayMs` from now.
export function useBanners(): { banner: Banner | null; show: (banner: Omit<Banner, "id">, delayMs?: number) => void } {
  const [queue, setQueue] = useState<Banner[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Set<number>());

  const show = useCallback((banner: Omit<Banner, "id">, delayMs = 0) => {
    const id = ++nextId.current;
    const timer = window.setTimeout(() => {
      timers.current.delete(timer);
      setQueue((queued) => [...queued, { ...banner, id }]);
    }, delayMs);
    timers.current.add(timer);
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const banner = queue[0] ?? null;
  useEffect(() => {
    if (!banner) return;
    const timer = window.setTimeout(() => setQueue((queued) => queued.slice(1)), banner.ms);
    return () => window.clearTimeout(timer);
  }, [banner]);

  return { banner, show };
}
