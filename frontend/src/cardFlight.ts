// Flies a copy of a hand card into a field slot. Imperative on purpose: the
// clone lives outside React's tree, so it keeps flying while React re-renders
// the hand from the server's response underneath it. Action cards resolve
// instantly and never show up in the field, so the flight ends by fading out
// at the slot instead of handing over to a rendered card.
export function flyCard(card: HTMLElement, slot: HTMLElement): void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const from = card.getBoundingClientRect();
  const to = slot.getBoundingClientRect();
  const clone = card.cloneNode(true) as HTMLElement;
  clone.classList.add("card-flight");
  Object.assign(clone.style, {
    left: `${from.left}px`,
    top: `${from.top}px`,
    width: `${from.width}px`,
    height: `${from.height}px`,
  });
  document.body.appendChild(clone);

  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);
  const scale = to.height / from.height;

  const flight = clone.animate(
    [
      { transform: "none", opacity: 1 },
      { transform: `translate(${dx / 2}px, ${dy / 2 - 60}px) rotate(-8deg) scale(1.05)`, opacity: 1, offset: 0.45 },
      { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 1, offset: 0.75 },
      { transform: `translate(${dx}px, ${dy - 16}px) scale(${scale})`, opacity: 0, filter: "brightness(2.5)" },
    ],
    { duration: 700, easing: "cubic-bezier(.3,.7,.3,1)" },
  );
  flight.onfinish = () => clone.remove();
  flight.oncancel = () => clone.remove();
}
