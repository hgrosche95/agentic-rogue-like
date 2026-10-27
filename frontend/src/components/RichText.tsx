import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ANY_KEYWORD, keyword, keywordFor } from "../keywords";

// `text` with every game term (keywords.ts) marked for the tooltip layer (see
// Tooltips). `focusable`: whether a term can be tabbed to - not inside a
// card face, whose card is a button of its own.
export function RichText({ text, focusable = true }: { text: string; focusable?: boolean }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(ANY_KEYWORD)) {
    const term = keywordFor(match[0]);
    if (!term) continue;
    parts.push(text.slice(last, match.index));
    parts.push(
      <span key={match.index} className="keyword" data-keyword={term.id} tabIndex={focusable ? 0 : undefined}>
        {match[0]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

const TIP_SELECTOR = "[data-keyword], [data-tip]";
const TOOLTIP_ID = "game-tooltip";
// how long a touch has to rest on a term before its tooltip opens, and how
// far it may wander meanwhile (a drag of the card it sits on cancels it)
const LONG_PRESS_MS = 450;
const LONG_PRESS_SLOP_PX = 8;
const EDGE_PX = 8;
const GAP_PX = 8;

function tipOf(el: Element): { term?: string; text: string } | null {
  const id = el.getAttribute("data-keyword");
  const known = id ? keyword(id) : undefined;
  if (known) return { term: known.term, text: known.text };
  const text = el.getAttribute("data-tip");
  return text ? { term: el.getAttribute("data-tip-term") ?? undefined, text } : null;
}

// One tooltip for the whole page: whatever term or [data-tip] is hovered,
// focused or long-pressed. It lives in a portal with a fixed position, so it
// isn't clipped by the card or overlay it belongs to, and follows its anchor
// (a hand card lifts on hover) while staying inside the window. The anchor
// is described by it (aria-describedby) while it shows.
export function Tooltips() {
  const [anchor, setAnchor] = useState<Element | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let press: { timer: number; x: number; y: number } | null = null;
    // a long press that opened a tooltip doesn't also click what it was on
    let swallowClick = false;
    const tipTarget = (target: EventTarget | null) =>
      (target as Element | null)?.closest?.(TIP_SELECTOR) ?? null;
    const cancelPress = () => {
      if (press) window.clearTimeout(press.timer);
      press = null;
    };

    function over(event: PointerEvent) {
      if (event.pointerType === "touch") return;
      setAnchor(tipTarget(event.target));
    }
    function down(event: PointerEvent) {
      cancelPress();
      const el = tipTarget(event.target);
      // a press - the start of a click or a drag - closes it (a term that
      // takes focus opens it again)
      setAnchor(null);
      if (!el || event.pointerType !== "touch") return;
      press = {
        x: event.clientX,
        y: event.clientY,
        timer: window.setTimeout(() => {
          press = null;
          swallowClick = true;
          setAnchor(el);
        }, LONG_PRESS_MS),
      };
    }
    function move(event: PointerEvent) {
      if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > LONG_PRESS_SLOP_PX) cancelPress();
    }
    function up() {
      cancelPress();
      // the click that may follow is dispatched before any timer runs
      if (swallowClick) window.setTimeout(() => (swallowClick = false), 0);
    }
    function click(event: MouseEvent) {
      if (!swallowClick) return;
      swallowClick = false;
      event.preventDefault();
      event.stopPropagation();
    }
    function contextMenu(event: MouseEvent) {
      if (tipTarget(event.target)) event.preventDefault();
    }
    const focusIn = (event: FocusEvent) => setAnchor(tipTarget(event.target));
    const hide = () => setAnchor(null);
    const key = (event: KeyboardEvent) => event.key === "Escape" && hide();

    document.addEventListener("pointerover", over);
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("pointermove", move, true);
    document.addEventListener("pointerup", up, true);
    document.addEventListener("pointercancel", up, true);
    window.addEventListener("click", click, true);
    document.addEventListener("contextmenu", contextMenu, true);
    document.addEventListener("focusin", focusIn);
    document.addEventListener("focusout", hide);
    document.addEventListener("keydown", key);
    window.addEventListener("scroll", hide, true);
    return () => {
      cancelPress();
      document.removeEventListener("pointerover", over);
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("pointermove", move, true);
      document.removeEventListener("pointerup", up, true);
      document.removeEventListener("pointercancel", up, true);
      window.removeEventListener("click", click, true);
      document.removeEventListener("contextmenu", contextMenu, true);
      document.removeEventListener("focusin", focusIn);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("keydown", key);
      window.removeEventListener("scroll", hide, true);
    };
  }, []);

  // the anchor names the tooltip as its description while it shows
  useEffect(() => {
    if (!anchor) return;
    const before = anchor.getAttribute("aria-describedby");
    anchor.setAttribute("aria-describedby", TOOLTIP_ID);
    return () => {
      if (before === null) anchor.removeAttribute("aria-describedby");
      else anchor.setAttribute("aria-describedby", before);
    };
  }, [anchor]);

  // Above the anchor, or under it where the top of the window leaves no
  // room; slid sideways to stay inside the window. Re-placed every frame, so
  // it follows a card lifting on hover - and goes once its anchor is gone.
  useLayoutEffect(() => {
    if (!anchor) return;
    let frame = 0;
    const place = () => {
      const el = box.current;
      if (!anchor.isConnected) {
        setAnchor(null);
        return;
      }
      if (el) {
        const at = anchor.getBoundingClientRect();
        const { width, height } = el.getBoundingClientRect();
        const below = at.top - height - GAP_PX < EDGE_PX;
        const left = Math.max(EDGE_PX, Math.min(window.innerWidth - width - EDGE_PX, at.left + at.width / 2 - width / 2));
        const top = below
          ? Math.min(window.innerHeight - height - EDGE_PX, at.bottom + GAP_PX)
          : at.top - height - GAP_PX;
        el.style.left = `${left}px`;
        el.style.top = `${top}px`;
        el.classList.toggle("is-below", below);
      }
      frame = requestAnimationFrame(place);
    };
    place();
    return () => cancelAnimationFrame(frame);
  }, [anchor]);

  const tip = anchor && tipOf(anchor);
  if (!tip) return null;
  return createPortal(
    <div ref={box} id={TOOLTIP_ID} className="tooltip" role="tooltip">
      {tip.term && <b className="tooltip-term">{tip.term}</b>}
      {tip.text}
    </div>,
    document.body,
  );
}
