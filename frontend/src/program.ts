import { QUEUED_TYPES, type Card, type PendingCombatView } from "./api";

// Program mode's rules as the frontend needs them (see the backend's
// combat.run_program) - shared by CombatPanel and ProgramLines.

// Whether playing `card` queues it into the program (combat.QUEUED_TYPES).
export function queues(combat: PendingCombatView, card: Card): boolean {
  return combat.program_mode && QUEUED_TYPES.includes(card.type);
}

// The order the queued lines will run in, and which of them run: a
// refactoring boss reverses it, an interrupting enemy cuts it short.
export function programPlan(combat: PendingCombatView, enemySlain: boolean) {
  const queuedLines = combat.program.flatMap((card, line) => (card ? [line] : []));
  const cutAfter = combat.enemy_interrupt_after;
  const reversed = combat.program_mode && combat.enemy_intent === "refactor" && !enemySlain;
  const runOrder = reversed ? [...queuedLines].reverse() : queuedLines;
  return {
    queuedLines,
    cutAfter,
    reversed,
    cutLines: cutAfter === null ? [] : runOrder.slice(cutAfter),
  };
}
