import { useState } from "react";

export interface HpExchange {
  id: number;
  playerDelta: number;
  enemyDelta: number;
}

// The server only sends the new state after each action, never "took 11
// damage" events - so derive what happened by comparing both HP values
// against the previous render. Tracking both sides together (instead of one
// hook per side) tells the arena who acted: an enemy HP drop means the player
// struck, a player HP drop means the enemy did. `id` bumps on every change so
// callers can use it as a React key and replay animations even when two hits
// in a row deal the same damage.
export function useHpExchange(playerHp: number, enemyHp: number): HpExchange | null {
  const [previous, setPrevious] = useState({ playerHp, enemyHp });
  const [exchange, setExchange] = useState<HpExchange | null>(null);

  if (playerHp !== previous.playerHp || enemyHp !== previous.enemyHp) {
    setPrevious({ playerHp, enemyHp });
    setExchange({
      id: (exchange?.id ?? 0) + 1,
      playerDelta: playerHp - previous.playerHp,
      enemyDelta: enemyHp - previous.enemyHp,
    });
  }

  return exchange;
}
