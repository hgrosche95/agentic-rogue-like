import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

// A press has to move this far before it counts as a drag - anything less
// stays a click, so tap-to-select keeps working.
const DRAG_THRESHOLD_PX = 8;

// Dragging a hand card onto a field slot. Pointer events rather than HTML5
// drag and drop, so it works with touch too and the card itself follows the
// pointer: a copy of it is lifted out of the hand, and dropping it over an
// empty slot (any element with data-slot-index) plays it there.
export function useCardDrag({
  enabled,
  onDrop,
}: {
  enabled: boolean;
  // `from` is the dragged copy, parked where it was dropped - the flight into
  // the slot starts from there. It is removed right after onDrop returns.
  onDrop: (handIndex: number, slotIndex: number, slot: HTMLElement, from: HTMLElement) => void;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [hoverSlot, setHoverSlot] = useState<number | null>(null);
  const justDragged = useRef(false);

  function slotAt(x: number, y: number): HTMLElement | null {
    return document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-slot-index]") ?? null;
  }

  function onPointerDown(event: ReactPointerEvent<HTMLElement>, handIndex: number) {
    if (!enabled || event.button !== 0) return;
    const card = event.currentTarget;
    const startX = event.clientX;
    const startY = event.clientY;
    let ghost: HTMLElement | null = null;

    const move = (e: PointerEvent) => {
      if (!ghost) {
        if (Math.hypot(e.clientX - startX, e.clientY - startY) < DRAG_THRESHOLD_PX) return;
        const rect = card.getBoundingClientRect();
        ghost = card.cloneNode(true) as HTMLElement;
        ghost.classList.add("card-drag");
        Object.assign(ghost.style, {
          left: `${rect.left}px`,
          top: `${rect.top}px`,
          width: `${rect.width}px`,
          height: `${rect.height}px`,
        });
        document.body.appendChild(ghost);
        setDragging(handIndex);
      }
      const dx = e.clientX - startX;
      ghost.style.transform = `translate(${dx}px, ${e.clientY - startY}px) rotate(${Math.max(-8, Math.min(8, dx / 25))}deg) scale(1.05)`;
      const slot = slotAt(e.clientX, e.clientY);
      setHoverSlot(slot ? Number(slot.dataset.slotIndex) : null);
    };

    const finish = (e: PointerEvent, drop: boolean) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      if (!ghost) return; // never left the threshold: an ordinary click
      // the click that may follow this pointerup is dispatched before any
      // timer runs, so the flag only ever swallows that one click
      justDragged.current = true;
      window.setTimeout(() => (justDragged.current = false), 0);
      setDragging(null);
      setHoverSlot(null);
      const slot = drop ? slotAt(e.clientX, e.clientY) : null;
      if (slot) {
        // park the copy where it was let go, without the drag transform, so
        // the flight into the slot starts right there
        const rect = ghost.getBoundingClientRect();
        Object.assign(ghost.style, { transform: "none", left: `${rect.left}px`, top: `${rect.top}px` });
        onDrop(handIndex, Number(slot.dataset.slotIndex), slot, ghost);
      }
      ghost.remove();
    };
    const up = (e: PointerEvent) => finish(e, true);
    const cancel = (e: PointerEvent) => finish(e, false);

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
  }

  // A drag that ends back on the card still fires a click there - swallow it.
  function consumeClick(): boolean {
    const was = justDragged.current;
    justDragged.current = false;
    return was;
  }

  return { dragging, hoverSlot, onPointerDown, consumeClick };
}
