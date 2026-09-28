// Game-feel effects: screen shake, hit flashes, projectiles, floating
// numbers, card flights between piles and hand, and a particle canvas.
// Everything is imperative (Web Animations API, a canvas, short-lived DOM
// nodes outside React's control), so hooking it into a component takes a
// call or two - the combat UI itself stays unaware of how effects look.
// All of it respects prefers-reduced-motion: no shake, flashes or particles,
// and numbers only fade.
import "./fx.css";
import { floatNumber, shake, type NumberKind, type Side } from "./arena";
import { cardPlayed } from "./director";

export { useCombatFx } from "./useCombatFx";

export const fx = {
  // a card left the hand for a field slot - call before the server answers
  cardPlayed,
  // shake an element (the arena, the whole panel); 0.2 light .. 2 Kernel Panic
  shake: (target: Element | null, intensity: number, delay = 0) => shake(target, intensity, delay),
  // a number popping up over a fighter in the arena
  damageNumber: (stage: HTMLElement, side: Side, amount: number, kind: NumberKind = "damage", delay = 0) =>
    floatNumber(stage, side, kind === "heal" || kind === "block" ? `+${amount}` : `-${amount}`, kind, { delay }),
};
