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
export function flyCard(card: HTMLElement, slot: HTMLElement, lands = false, pile?: PileKind): void {
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
  flight.oncancel = () => clone.remove();
  // an action burns out in its slot, then what is left of it goes on to its
  // pile - the Graveyard, or the Banished pile for a one-shot
  flight.onfinish = () => {
    const target = pile ? pileFace(pile) : null;
    if (lands || !target) {
      clone.remove();
      return;
    }
    const end = { dx, dy: dy - 14, scale: fit * 1.08 };
    toPile(clone, target, pile ?? "graveyard", width, height, cx, cy, end);
  };
}

export type PileKind = "graveyard" | "banished";

const PILE_CLASS: Record<PileKind, string> = { graveyard: "pile-graveyard", banished: "pile-banished" };
const PILE_MS = 420;

function pileFace(kind: PileKind): HTMLElement | null {
  return document.querySelector<HTMLElement>(`.${PILE_CLASS[kind]} .pile-face`);
}

// A pixel mask that keeps a card's middle and eats away at its edges - a
// card dissolving into the Banished pile (made once, then reused).
let dissolveMask: string | null = null;
function pixelMask(): string {
  if (dissolveMask) return dissolveMask;
  const canvas = document.createElement("canvas");
  canvas.width = 16;
  canvas.height = 22;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "none";
  for (let y = 0; y < 22; y++)
    for (let x = 0; x < 16; x++) {
      const edge = Math.min(x, 15 - x, y, 21 - y) / 8;
      if (Math.random() < 0.25 + edge * 0.6) ctx.fillRect(x, y, 1, 1);
    }
  dissolveMask = `url(${canvas.toDataURL()})`;
  return dissolveMask;
}

// The second leg: from where the card resolved (its clone at `end`) down to
// the pile, shrinking - a used-up card falls apart into pixels on the way.
function toPile(
  clone: HTMLElement,
  pile: HTMLElement,
  kind: PileKind,
  width: number,
  height: number,
  cx: number,
  cy: number,
  end: { dx: number; dy: number; scale: number },
): void {
  const to = pile.getBoundingClientRect();
  const px = to.left + to.width / 2 - cx;
  const py = to.top + to.height / 2 - cy;
  const small = Math.min(to.width / width, to.height / height) * 0.9;
  if (kind === "banished") {
    clone.style.setProperty("mask-image", pixelMask());
    clone.style.setProperty("-webkit-mask-image", pixelMask());
    clone.style.setProperty("mask-size", "100% 100%");
    clone.style.setProperty("-webkit-mask-size", "100% 100%");
    clone.style.imageRendering = "pixelated";
    sparks(to, "var(--danger, #ff4f8b)");
  }
  const leg = clone.animate(
    [
      { transform: `translate(${end.dx}px, ${end.dy}px) scale(${end.scale})`, opacity: 0.85, filter: "brightness(1.4)" },
      {
        transform: `translate(${(end.dx + px) / 2}px, ${Math.min(end.dy, py) - 40}px) rotate(-8deg) scale(${(end.scale + small) / 2})`,
        opacity: 0.85,
        offset: 0.5,
      },
      { transform: `translate(${px}px, ${py}px) rotate(-12deg) scale(${small})`, opacity: kind === "banished" ? 0 : 0.6 },
    ],
    { duration: PILE_MS, easing: "cubic-bezier(0.5, 0, 0.75, 0.4)" },
  );
  leg.onfinish = () => clone.remove();
  leg.oncancel = () => clone.remove();
}

// A few pixels thrown up from a pile - a card coming apart on it.
function sparks(at: DOMRect, color: string): void {
  const x = at.left + at.width / 2;
  const y = at.top + at.height / 2;
  for (let i = 0; i < 14; i++) {
    const bit = document.createElement("i");
    bit.className = "pile-spark";
    bit.style.left = `${x}px`;
    bit.style.top = `${y}px`;
    bit.style.background = color;
    document.body.appendChild(bit);
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * 2.2;
    const reach = 26 + Math.random() * 46;
    const spark = bit.animate(
      [
        { transform: "translate(0, 0)", opacity: 1 },
        { transform: `translate(${Math.cos(angle) * reach}px, ${Math.sin(angle) * reach}px)`, opacity: 0 },
      ],
      { duration: 420 + Math.random() * 260, delay: PILE_MS * 0.6, easing: "cubic-bezier(0.2, 0.7, 0.3, 1)", fill: "backwards" },
    );
    spark.onfinish = () => bit.remove();
    spark.oncancel = () => bit.remove();
  }
}

// A card taken off the field without coming back to the hand - destroyed,
// banished or uninstalled: its last picture (`ghost`, a copy of the slot's
// card made before it went) comes apart on its way into the Banished pile.
export function dissolveToBanished(ghost: HTMLElement, from: DOMRect): void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const target = pileFace("banished");
  if (!target) return;
  const width = from.width;
  const height = from.height;
  ghost.classList.add("card-flight");
  ghost.removeAttribute("style");
  Object.assign(ghost.style, { left: `${from.left}px`, top: `${from.top}px`, width: `${width}px`, height: `${height}px` });
  document.body.appendChild(ghost);
  toPile(ghost, target, "banished", width, height, from.left + width / 2, from.top + height / 2, { dx: 0, dy: 0, scale: 1 });
}


// A bought card (or artifact) flies up into what it joins - the deck button
// in the top bar, or the artifact shelf - and that bumps as it lands.
export function flyInto(item: HTMLElement, target: HTMLElement | null): void {
  if (!target || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const from = item.getBoundingClientRect();
  const to = target.getBoundingClientRect();
  const clone = item.cloneNode(true) as HTMLElement;
  clone.classList.add("card-flight");
  clone.removeAttribute("style");
  Object.assign(clone.style, {
    left: `${from.left}px`,
    top: `${from.top}px`,
    width: `${from.width}px`,
    height: `${from.height}px`,
  });
  document.body.appendChild(clone);
  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);
  const scale = Math.min(to.width / from.width, to.height / from.height);
  const flight = clone.animate(
    [
      { transform: "none", opacity: 1, filter: "brightness(1.3)" },
      { transform: `translate(${dx * 0.35}px, ${dy * 0.35 - 60}px) rotate(-8deg) scale(0.75)`, opacity: 1, offset: 0.4 },
      { transform: `translate(${dx}px, ${dy}px) rotate(-14deg) scale(${scale})`, opacity: 0.2, filter: "brightness(2)" },
    ],
    { duration: 620, easing: "cubic-bezier(0.45, 0, 0.3, 1)" },
  );
  const land = () => {
    clone.remove();
    target.animate(
      [{ transform: "scale(1)" }, { transform: "scale(1.18)", filter: "brightness(1.6)" }, { transform: "scale(1)" }],
      { duration: 360, easing: "ease-out" },
    );
  };
  flight.onfinish = land;
  flight.oncancel = () => clone.remove();
}
