// Cards and artifacts on offer lean towards the pointer, and a light
// (--glare-x/y) slides over them - one listener for the whole page instead
// of a hook in every screen. The lean is set through CSS variables that
// flair.css turns into the `rotate` property, which composes with the
// transforms the deal, flip and pick animations run.
//
// Only offers are tilted, never the hand: hand cards are dragged, and a
// card that leans away under the pointer is harder to grab.

const TILTABLE = ".reward-card, .deck-card, .artifact-card, .kit-option";
// how far a card leans at its edge (degrees)
const MAX_TILT = 9;

let current: HTMLElement | null = null;

function reset(el: HTMLElement) {
  el.style.removeProperty("--tilt");
  el.style.removeProperty("--glare-x");
  el.style.removeProperty("--glare-y");
  el.classList.remove("is-tilted");
}

function onMove(event: PointerEvent) {
  if (event.pointerType === "touch") return;
  const target = event.target instanceof Element ? (event.target.closest(TILTABLE) as HTMLElement | null) : null;
  if (current && current !== target) reset(current);
  current = target;
  if (!target || (target as HTMLButtonElement).disabled) return;
  const box = target.getBoundingClientRect();
  if (box.width === 0 || box.height === 0) return;
  // -1..1 from the card's centre
  const dx = Math.max(-1, Math.min(1, ((event.clientX - box.left) / box.width) * 2 - 1));
  const dy = Math.max(-1, Math.min(1, ((event.clientY - box.top) / box.height) * 2 - 1));
  const amount = Math.min(1, Math.hypot(dx, dy));
  // the axis is perpendicular to the pointer's offset, so the near edge dips
  target.style.setProperty("--tilt", `${(-dy).toFixed(3)} ${dx.toFixed(3)} 0 ${(amount * MAX_TILT).toFixed(2)}deg`);
  target.style.setProperty("--glare-x", `${((dx + 1) * 50).toFixed(1)}%`);
  target.style.setProperty("--glare-y", `${((dy + 1) * 50).toFixed(1)}%`);
  target.classList.add("is-tilted");
}

export function enableCardTilt() {
  if (typeof window === "undefined") return;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  const handler = (event: PointerEvent) => {
    if (reduced?.matches) return;
    onMove(event);
  };
  document.addEventListener("pointermove", handler, { passive: true });
  document.addEventListener("pointerleave", () => current && reset(current));
}
