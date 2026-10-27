import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { HandCardView } from "../api";

// The server numbers the hand by position (hand_index), so after a card is
// played every card right of it comes back with a new index. Keyed by that,
// React would keep each DOM card where it is and swap the faces on it - the
// table would snap instead of sliding. These keys follow the cards
// themselves: each new hand is matched against the last one in order, by
// card id, and only cards that weren't there before get a new key.
interface Keyed {
  hand: HandCardView[];
  keys: string[];
  next: number;
}

function rekey(last: Keyed, hand: HandCardView[]): Keyed {
  const keys: string[] = [];
  let next = last.next;
  let from = 0;
  for (const card of hand) {
    const at = last.hand.findIndex((old, i) => i >= from && old.id === card.id);
    if (at >= 0) {
      keys.push(last.keys[at]);
      from = at + 1;
    } else {
      keys.push(`card-${next++}`);
    }
  }
  return { hand, keys, next };
}

export function useStableHandKeys(hand: HandCardView[]): string[] {
  const [keyed, setKeyed] = useState<Keyed>(() => ({
    hand,
    keys: hand.map((_, i) => `card-${i}`),
    next: hand.length,
  }));
  if (keyed.hand === hand) return keyed.keys;
  // a new hand from the server: worked out during render (React's pattern
  // for state derived from the previous props), so the first paint of it is
  // already keyed right
  const updated = rekey(keyed, hand);
  setKeyed(updated);
  return updated.keys;
}

const SLIDE_MS = 320;
const DEAL_MS = 380;
const DEAL_STAGGER_MS = 70;
const EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";

// FLIP for the hand: after every re-layout (a card played or discarded,
// cards drawn), each card that moved starts from where it was and slides
// to its new place; cards that just arrived are dealt in from the Source pile
// on the left. Only the `translate` property is animated - composited, and
// separate from the fan's own transform (rotate and lift), which keeps
// easing on its own. `[data-flip-key]` marks the cards inside `container`.
export function useHandFlip(container: RefObject<HTMLElement | null>, layout: string) {
  const last = useRef<Map<string, { x: number; y: number }> | null>(null);
  useLayoutEffect(() => {
    const root = container.current;
    if (!root) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const before = last.current;
    const now = new Map<string, { x: number; y: number }>();
    let dealt = 0;
    root.querySelectorAll<HTMLElement>("[data-flip-key]").forEach((card) => {
      // hidden (a played card on its way out) - not part of the layout
      if (card.offsetParent === null) return;
      const key = card.dataset.flipKey ?? "";
      // offsetLeft/Top: the layout box, without the fan's or a hover's transform
      const at = { x: card.offsetLeft, y: card.offsetTop };
      now.set(key, at);
      if (reduced) return;
      const was = before?.get(key);
      if (was) {
        const dx = was.x - at.x;
        const dy = was.y - at.y;
        if (dx === 0 && dy === 0) return;
        card.animate([{ translate: `${dx}px ${dy}px` }, { translate: "0 0" }], {
          duration: SLIDE_MS,
          easing: EASE_OUT,
          composite: "add",
        });
      } else {
        card.animate(
          [
            { translate: "-160px 40px", opacity: 0, scale: "0.85" },
            { translate: "0 0", opacity: 1, scale: "1" },
          ],
          { duration: DEAL_MS, delay: dealt++ * DEAL_STAGGER_MS, easing: EASE_OUT, fill: "backwards" },
        );
      }
    });
    last.current = now;
  }, [container, layout]);
}
