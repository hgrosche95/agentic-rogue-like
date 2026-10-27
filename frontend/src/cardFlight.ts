import { sfx } from "./audio";

// how long a played card is in the air - the card waiting in its slot
// (.is-landing in App.css/neon.css) fades in as the flight touches down
export const FLIGHT_MS = 640;

// Flies a copy of a hand card into a field slot. Imperative on purpose: the
// clone lives outside React's tree, so it keeps flying while React re-renders
// the hand from the server's response underneath it. `lands`: the card stays
// in the slot (a permanent, a queued program line) - the copy settles exactly
// onto it and hands over to the rendered card. Otherwise (an action, which
// resolves instantly and never shows up in the field) it flares and fades
// out at the slot.
export function flyCard(card: HTMLElement, slot: HTMLElement, lands = false): void {
  // reduced motion skips the flight, not its sound
  sfx.play("card_flight");
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  // The card's own box, centred where it is drawn: its bounding rect is
  // bigger than the card while the fan turns it, and the copy (outside the
  // fan) starts straight - so it starts at the card's size and turn instead.
  const rect = card.getBoundingClientRect();
  const width = card.offsetWidth || rect.width;
  const height = card.offsetHeight || rect.height;
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const turn = parseFloat(getComputedStyle(card).getPropertyValue("--rot")) || 0;
  const to = slot.getBoundingClientRect();
  const clone = card.cloneNode(true) as HTMLElement;
  clone.classList.add("card-flight");
  clone.removeAttribute("style");
  Object.assign(clone.style, {
    left: `${cx - width / 2}px`,
    top: `${cy - height / 2}px`,
    width: `${width}px`,
    height: `${height}px`,
  });
  document.body.appendChild(clone);

  const dx = to.left + to.width / 2 - cx;
  const dy = to.top + to.height / 2 - cy;
  // shrunk to fit the slot (or into the thin bar of the program's background)
  const fit = Math.min(to.width / width, to.height / height);
  const arc = Math.min(80, Math.abs(dy) * 0.35 + 30);

  const flight = clone.animate(
    lands
      ? [
          { transform: `rotate(${turn}deg)`, opacity: 1 },
          { transform: `translate(${dx * 0.45}px, ${dy * 0.45 - arc}px) rotate(-6deg) scale(1.04)`, opacity: 1, offset: 0.45 },
          { transform: `translate(${dx}px, ${dy}px) scale(${fit})`, opacity: 1, offset: 0.85 },
          { transform: `translate(${dx}px, ${dy}px) scale(${fit})`, opacity: 0 },
        ]
      : [
          { transform: `rotate(${turn}deg)`, opacity: 1 },
          { transform: `translate(${dx * 0.45}px, ${dy * 0.45 - arc}px) rotate(-6deg) scale(1.04)`, opacity: 1, offset: 0.45 },
          { transform: `translate(${dx}px, ${dy}px) scale(${fit})`, opacity: 1, filter: "brightness(1.6)", offset: 0.78 },
          { transform: `translate(${dx}px, ${dy - 14}px) scale(${fit * 1.08})`, opacity: 0, filter: "brightness(2.4)" },
        ],
    { duration: FLIGHT_MS, easing: "cubic-bezier(0.45, 0, 0.25, 1)" },
  );
  flight.onfinish = () => clone.remove();
  flight.oncancel = () => clone.remove();
}
