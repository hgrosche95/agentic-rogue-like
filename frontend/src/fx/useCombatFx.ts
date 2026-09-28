import { useEffect, useRef, type RefObject } from "react";
import type { PendingCombatView } from "../api";
import { combatStarted, enemyDefeated, reactToCombat, snapshotOf, type CombatSnapshot } from "./director";

// Plugs the effects into the combat panel: every new server state is
// compared with the previous one and turned into effects. Runs after React
// has committed, so the effects can measure the new layout (new hand cards,
// a permanent in its slot).
export function useCombatFx(
  panelRef: RefObject<HTMLElement | null>,
  combat: PendingCombatView,
  playerHp: number,
  log: string[],
  { boss = false, slain = false }: { boss?: boolean; slain?: boolean } = {},
): void {
  const previous = useRef<CombatSnapshot | null>(null);

  useEffect(() => {
    const panel = panelRef.current;
    const before = previous.current;
    const after = snapshotOf(combat, playerHp, log.length);
    previous.current = after;
    if (!panel) return;
    if (!before || before.enemyName !== combat.enemy_name) {
      combatStarted(panel);
      return;
    }
    if (after.logLength === before.logLength && after.hand === before.hand) return;
    reactToCombat(panel, before, after, log.slice(before.logLength), { boss });
  }, [panelRef, combat, playerHp, log, boss]);

  useEffect(() => {
    if (slain && panelRef.current) enemyDefeated(panelRef.current);
  }, [panelRef, slain]);
}
