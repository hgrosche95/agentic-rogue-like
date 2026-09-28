import { centerOf, div, reducedMotion, spawn, type Point } from "./motion";
import { disintegrate, emit } from "./particles";

// Effects on the card table below the arena: cards travelling between the
// piles and the hand, one-shot cards dissolving, permanents booting up.

export type PileKind = "deck" | "graveyard" | "banished";

export function pileEl(panel: HTMLElement, kind: PileKind): HTMLElement | null {
  return panel.querySelector<HTMLElement>(`.pile-${kind} .pile-face`);
}

export function slotEls(panel: HTMLElement): HTMLElement[] {
  return [...panel.querySelectorAll<HTMLElement>(".field > .field-slot")];
}

export function handCardEl(panel: HTMLElement, handIndex: number): HTMLElement | null {
  return panel.querySelector<HTMLElement>(`.hand [data-hand-index="${handIndex}"]`);
}

// A pile acknowledging a card arriving: it jumps and glows.
export function pulsePile(el: HTMLElement | null, color: string, delay = 0): void {
  if (!el || reducedMotion()) return;
  el.animate(
    [
      { transform: "none", boxShadow: "none" },
      { transform: "scale(1.12) translateY(-3px)", boxShadow: `0 0 18px ${color}`, offset: 0.3 },
      { transform: "none", boxShadow: "none" },
    ],
    { duration: 420, delay, easing: "ease-out" },
  );
}

// A snapshot of a card as it looked before the server's answer re-rendered
// the table: a detached clone plus where it was.
export interface CardGhost {
  node: HTMLElement;
  rect: DOMRect;
}

export function snapshotCard(el: HTMLElement): CardGhost {
  const node = el.cloneNode(true) as HTMLElement;
  node.classList.remove("is-selected", "is-played");
  node.removeAttribute("data-hand-index");
  return { node, rect: el.getBoundingClientRect() };
}

function mount(ghost: CardGhost, rect: DOMRect = ghost.rect): HTMLElement {
  const node = ghost.node.cloneNode(true) as HTMLElement;
  node.classList.add("fx-ghost");
  Object.assign(node.style, {
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${ghost.rect.width}px`,
    height: `${ghost.rect.height}px`,
  });
  return node;
}

// A played one-shot card at its slot: it glitches, is eaten by a scan line
// and its pixels stream into the banished pile.
export function dissolveToPile(ghost: CardGhost, at: DOMRect, pile: HTMLElement | null, delay = 0): void {
  if (reducedMotion()) return;
  // the ghost is card-sized; centre it on the (smaller) slot
  const rect = new DOMRect(
    at.left + at.width / 2 - ghost.rect.width / 2,
    at.top + at.height / 2 - ghost.rect.height / 2,
    ghost.rect.width,
    ghost.rect.height,
  );
  const node = mount(ghost, rect);
  node.style.transform = `scale(${at.height / ghost.rect.height})`;
  const scale = at.height / ghost.rect.height;
  spawn(
    document.body,
    node,
    [
      { opacity: 1, clipPath: "inset(0 0 0 0)", filter: "none", transform: `scale(${scale})` },
      { opacity: 1, clipPath: "inset(0 0 0 0)", filter: "brightness(2) hue-rotate(-20deg)", transform: `scale(${scale}) translateX(-3px)`, offset: 0.15 },
      { opacity: 1, clipPath: "inset(0 0 0 0)", filter: "brightness(1.4)", transform: `scale(${scale}) translateX(3px)`, offset: 0.25 },
      { opacity: 0.6, clipPath: "inset(100% 0 0 0)", filter: "brightness(3)", transform: `scale(${scale})` },
    ],
    { duration: 700, delay, easing: "steps(10, end)" },
  );
  const scaled = new DOMRect(rect.left + (rect.width * (1 - scale)) / 2, rect.top + (rect.height * (1 - scale)) / 2, rect.width * scale, rect.height * scale);
  disintegrate(scaled, {
    count: 70,
    colors: ["#c65a3a", "#ff4d6a", "#ecdfc0", "#4fd8e0"],
    to: pile ? centerOf(pile) : undefined,
    delay: delay + 120,
  });
  pulsePile(pile, "rgba(255, 77, 106, 0.8)", delay + 900);
}

// A card flying off to a pile (an action card to the graveyard, a card lost
// to a discard cost).
export function flyToPile(ghost: CardGhost, from: DOMRect, pile: HTMLElement | null, delay = 0, color = "rgba(224, 168, 63, 0.8)"): void {
  if (!pile || reducedMotion()) return;
  const node = mount(ghost, new DOMRect(from.left + from.width / 2 - ghost.rect.width / 2, from.top + from.height / 2 - ghost.rect.height / 2, ghost.rect.width, ghost.rect.height));
  const start = from.height / ghost.rect.height;
  const target = pile.getBoundingClientRect();
  const dx = target.left + target.width / 2 - (from.left + from.width / 2);
  const dy = target.top + target.height / 2 - (from.top + from.height / 2);
  const end = target.height / ghost.rect.height;
  spawn(
    document.body,
    node,
    [
      { transform: `scale(${start})`, opacity: 1 },
      { transform: `translate(${dx * 0.5}px, ${dy * 0.5 - 40}px) rotate(${dx > 0 ? 12 : -12}deg) scale(${(start + end) / 2})`, opacity: 1, offset: 0.5 },
      { transform: `translate(${dx}px, ${dy}px) rotate(${dx > 0 ? 24 : -24}deg) scale(${end})`, opacity: 0.2 },
    ],
    { duration: 520, delay, easing: "cubic-bezier(.4,0,.6,1)" },
  );
  pulsePile(pile, color, delay + 480);
}

// New cards arriving in the hand from `pile`: each real hand card flies in
// from the pile to where React already laid it out (FLIP). A rewind (cards
// taken back out of the graveyard/banished pile) spins backwards through a
// cyan scan trail.
export function dealIn(cards: HTMLElement[], pile: HTMLElement | null, { rewind = false, delay = 0 } = {}): void {
  if (!pile || reducedMotion()) return;
  const from = pile.getBoundingClientRect();
  cards.forEach((card, i) => {
    const to = card.getBoundingClientRect();
    const dx = from.left + from.width / 2 - (to.left + to.width / 2);
    const dy = from.top + from.height / 2 - (to.top + to.height / 2);
    const s = from.height / to.height;
    const wait = delay + i * 110;
    const spin = rewind ? 540 : dx > 0 ? 14 : -14;
    card.animate(
      rewind
        ? [
            { transform: `translate(${dx}px, ${dy}px) scale(${s}) rotate(${spin}deg)`, opacity: 0, filter: "brightness(3) hue-rotate(160deg)" },
            { transform: `translate(${dx * 0.4}px, ${dy * 0.4 - 50}px) scale(1.1) rotate(${spin / 4}deg)`, opacity: 1, filter: "brightness(2) hue-rotate(90deg)", offset: 0.6 },
            { transform: "none", opacity: 1, filter: "none" },
          ]
        : [
            { transform: `translate(${dx}px, ${dy}px) scale(${s}) rotateY(90deg)`, opacity: 0 },
            { transform: `translate(${dx * 0.5}px, ${dy * 0.5 - 30}px) scale(0.9) rotate(${spin}deg)`, opacity: 1, offset: 0.55 },
            { transform: "translateY(-10px)", opacity: 1, offset: 0.85 },
            { transform: "none", opacity: 1 },
          ],
      { duration: rewind ? 620 : 480, delay: wait, easing: "cubic-bezier(.25,.8,.35,1)", fill: "backwards" },
    );
    if (rewind) {
      // the trail of the rewind: cyan pixels racing back along its path
      const start = centerOf(pile);
      const end = { x: to.left + to.width / 2, y: to.top + to.height / 2 };
      for (let k = 0; k < 16; k++) {
        emit({
          x: start.x + (Math.random() - 0.5) * 30,
          y: start.y + (Math.random() - 0.5) * 30,
          to: end,
          via: { x: (start.x + end.x) / 2, y: Math.min(start.y, end.y) - 70 },
          ttl: 480,
          delay: wait + k * 18,
          size: 3 + Math.random() * 3,
          color: k % 2 ? "#8ff2ef" : "#e6fcff",
          glow: true,
        });
      }
    }
  });
  pulsePile(pile, rewind ? "rgba(143, 242, 239, 0.9)" : "rgba(224, 168, 63, 0.7)", delay);
}

// A permanent card powering up in its slot: a scan line wipes over it and a
// terminal "boot" readout flickers on top.
export function bootSlot(slot: HTMLElement | undefined, label: string, delay = 0): void {
  if (!slot || reducedMotion()) return;
  const r = slot.getBoundingClientRect();
  const overlay = div("fx-boot");
  Object.assign(overlay.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
  overlay.innerHTML = `<span class="fx-boot-scan"></span><span class="fx-boot-text">&gt; ${label}<br/>[ OK ]</span>`;
  spawn(document.body, overlay, [{ opacity: 1 }, { opacity: 1, offset: 0.75 }, { opacity: 0 }], { duration: 900, delay });
  slot.animate(
    [
      { filter: "brightness(0.2) saturate(0)" },
      { filter: "brightness(2.2)", offset: 0.35 },
      { filter: "brightness(0.8)", offset: 0.5 },
      { filter: "brightness(1.4)", offset: 0.65 },
      { filter: "none" },
    ],
    { duration: 800, delay, easing: "steps(8, end)" },
  );
}

// A slot "firing": a permanent doing its job at the end of the turn.
export function pulseSlot(slot: HTMLElement | undefined, color: string, delay = 0): void {
  if (!slot || reducedMotion()) return;
  slot.animate(
    [
      { transform: "none", boxShadow: "none", filter: "none" },
      { transform: "translateY(-6px) scale(1.06)", boxShadow: `0 0 22px ${color}`, filter: "brightness(1.6)", offset: 0.3 },
      { transform: "none", boxShadow: "none", filter: "none" },
    ],
    { duration: 520, delay, easing: "ease-out" },
  );
}

// Pixels streaming from each slot to a point - Botnet drones, daemon shots,
// Mainframe's block flowing to the player. `onHit` runs as each wave lands.
export function streamFrom(
  slots: HTMLElement[],
  to: Point,
  { color = "#ff9a4d", perSlot = 6, delay = 0, drone = false, onHit }: { color?: string; perSlot?: number; delay?: number; drone?: boolean; onHit?: (i: number) => void } = {},
): void {
  if (reducedMotion()) {
    slots.forEach((_, i) => onHit && window.setTimeout(() => onHit(i), delay));
    return;
  }
  slots.forEach((slot, i) => {
    const start = centerOf(slot);
    for (let k = 0; k < perSlot; k++) {
      const lift = 120 + Math.random() * 140;
      emit({
        x: start.x + (Math.random() - 0.5) * 30,
        y: start.y - 20,
        to: { x: to.x + (Math.random() - 0.5) * 40, y: to.y + (Math.random() - 0.5) * 50 },
        via: { x: (start.x + to.x) / 2 + (Math.random() - 0.5) * 200, y: Math.min(start.y, to.y) - lift },
        ttl: 520 + Math.random() * 160,
        delay: delay + i * 120 + k * (drone ? 45 : 25),
        size: drone ? (k % 2 === 0 ? 14 : 6) : 4,
        color: k % 3 === 0 ? "#ffffff" : color,
        glyph: drone && k % 2 === 0 ? "◆" : undefined,
        glow: true,
        onArrive: k === 0 && onHit ? () => onHit(i) : undefined,
      });
    }
  });
}

// Every permanent on the field coming apart - Kernel Panic's price. Uses
// ghosts taken before the server cleared the field.
export function crumbleField(ghosts: CardGhost[], banished: HTMLElement | null, delay = 0): void {
  if (reducedMotion()) return;
  ghosts.forEach((ghost, i) => {
    const node = mount(ghost);
    const wait = delay + i * 70;
    spawn(
      document.body,
      node,
      [
        { opacity: 1, filter: "none", transform: "none", clipPath: "inset(0 0 0 0)" },
        { opacity: 1, filter: "brightness(2.5) hue-rotate(180deg)", transform: "translateX(-4px) skewX(8deg)", offset: 0.2 },
        { opacity: 1, filter: "brightness(1.5)", transform: "translateX(4px)", clipPath: "inset(0 0 0 0)", offset: 0.35 },
        { opacity: 0.3, filter: "brightness(3)", transform: "none", clipPath: "inset(0 0 100% 0)" },
      ],
      { duration: 650, delay: wait, easing: "steps(9, end)" },
    );
    disintegrate(ghost.rect, {
      count: 50,
      colors: ["#1f4fd8", "#e6fcff", "#4fd8e0", "#ff4d6a"],
      delay: wait + 150,
      to: i % 2 === 0 && banished ? centerOf(banished) : undefined,
    });
  });
  pulsePile(banished, "rgba(255, 77, 106, 0.8)", delay + 1000);
}
