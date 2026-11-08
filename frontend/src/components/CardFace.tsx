import { useContext, useLayoutEffect, useRef, type ReactNode } from "react";
import { CONTROL_FLOW_TYPES, PERMANENT_CARD_TYPES, QUEUED_TYPES, type Card, type CardType } from "../api";
import { ShowTokensContext } from "../characters";
import { ProgramModeContext, useCardText } from "../program";
import { unitOf } from "../readouts";
import { RichText } from "./RichText";

// Each card is a module: a drawn type icon in the socket top left (where
// other deckbuilders put a cost - this game has none, except the
// Vibe-Coder's tokens, bottom left), and, in combat, a readout with the
// number the card will really come out with.

type Kind = "strike" | "shield" | "repair" | "purge" | "flow" | "module" | "control";

function kindOf(type: CardType): Kind {
  if (PERMANENT_CARD_TYPES.includes(type)) return "module";
  if (CONTROL_FLOW_TYPES.includes(type)) return "control";
  if (type === "attack") return "strike";
  if (type === "block") return "shield";
  if (type === "heal") return "repair";
  if (type === "final_strike") return "purge";
  return "flow";
}

const KIND_LABEL: Record<Kind, string> = {
  strike: "Attack",
  shield: "Block",
  repair: "Heal",
  purge: "Finisher",
  flow: "Card flow",
  module: "Permanent",
  control: "Control flow",
};

// The line under a card's name: what kind of card it is, so the effect text
// can start with what the card does. Permanents add when they act.
const TYPE_LINE: Record<Kind, string> = {
  strike: "Attack",
  shield: "Block",
  repair: "Heal",
  purge: "Finisher",
  flow: "Card flow",
  module: "Permanent",
  control: "Control flow",
};

// (a one-shot says so with its 1× tag at the card's foot; a permanent with
// the turning arrows in front of its line - it works every turn)
// In a program, card flow is the one kind that doesn't wait for the program:
// it takes effect the moment it is played, and its line says so.
function typeLine(card: Card, program: boolean): { label: string; repeats: boolean; instant: boolean } {
  if (card.type === "glitch") return { label: "Junk", repeats: false, instant: false };
  const kind = kindOf(card.type);
  const instant = program && !QUEUED_TYPES.includes(card.type) && !PERMANENT_CARD_TYPES.includes(card.type);
  if (instant) return { label: "Instant", repeats: false, instant };
  return { label: TYPE_LINE[kind], repeats: kind === "module", instant };
}

// The number a card without a readout (card flow, permanents, control
// flow) is about, big, with what it counts - from the card's own value, so
// an upgrade shows up here too. Types whose value is no count are left out.
type StatIcon = "cards" | "percent" | "shield" | "damage" | "token" | "clock";
const STAT: Partial<
  Record<CardType, { icon: StatIcon; unit: string; sign?: "+" | "−"; percent?: boolean; half?: boolean }>
> = {
  draw: { icon: "cards", unit: "draw" },
  retrieve: { icon: "cards", unit: "back" },
  restore: { icon: "cards", unit: "back" },
  amplifier: { icon: "percent", unit: "boost", sign: "+", percent: true },
  armor: { icon: "shield", unit: "dmg taken", sign: "−" },
  draw_bonus: { icon: "cards", unit: "per turn", sign: "+" },
  damage_boost: { icon: "damage", unit: "per permanent", sign: "+" },
  turret: { icon: "damage", unit: "per turn" },
  fortify: { icon: "shield", unit: "per permanent", sign: "+" },
  compact: { icon: "token", unit: "tokens back" },
  free_play: { icon: "token", unit: "free cards" },
  chain: { icon: "damage", unit: "per card", sign: "+" },
  token_regen: { icon: "token", unit: "per turn", sign: "+" },
  opener: { icon: "token", unit: "free / turn" },
  // its value counts half blocks (2: one block per Malware)
  quarantine: { icon: "shield", unit: "per malware", sign: "+", half: true },
  recycle: { icon: "cards", unit: "per banish" },
  pipe: { icon: "damage", unit: "per action", sign: "+" },
  batch: { icon: "token", unit: "per action" },
  buffer: { icon: "clock", unit: "stored" },
  flush: { icon: "damage", unit: "stored dmg", sign: "+", percent: true },
  goto: { icon: "cards", unit: "replayed" },
};

function StatGlyph({ icon }: { icon: StatIcon }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="card-stat-icon">
      {icon === "cards" && (
        <>
          <rect x="7.5" y="2.5" width="9" height="12" rx="1.5" />
          <rect x="3.5" y="5.5" width="9" height="12" rx="1.5" className="cut" />
        </>
      )}
      {icon === "percent" && (
        <>
          <circle cx="6" cy="6" r="2.4" />
          <circle cx="14" cy="14" r="2.4" />
          <path d="M15.5 4.5 4.5 15.5" />
        </>
      )}
      {icon === "shield" && <path d="M10 2.4 16 4.8v4.6c0 4-2.7 6.8-6 8.2-3.3-1.4-6-4.2-6-8.2V4.8Z" />}
      {icon === "damage" && (
        <>
          <circle cx="10" cy="10" r="5.2" />
          <path d="M10 1.8v4M10 14.2v4M1.8 10h4M14.2 10h4" />
        </>
      )}
      {icon === "token" && (
        <>
          <path d="M6 4h8l3 6-3 6H6l-3-6Z" />
          <path d="M8 10h4" />
        </>
      )}
      {icon === "clock" && (
        <>
          <circle cx="10" cy="10" r="7" />
          <path d="M10 6v4l3 2" />
        </>
      )}
    </svg>
  );
}

export function CardTypeIcon({ type }: { type: CardType }) {
  const kind = kindOf(type);
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={`card-icon is-${kind}`}>
      {kind === "strike" && (
        <>
          <circle cx="10" cy="10" r="5.2" />
          <path d="M10 1.8v4M10 14.2v4M1.8 10h4M14.2 10h4" />
          <circle cx="10" cy="10" r="1.2" className="fill" />
        </>
      )}
      {kind === "shield" && <path d="M10 2.4 16 4.8v4.6c0 4-2.7 6.8-6 8.2-3.3-1.4-6-4.2-6-8.2V4.8Z" />}
      {kind === "repair" && <path d="M7.6 3h4.8v4.6H17v4.8h-4.6V17H7.6v-4.6H3V7.6h4.6Z" />}
      {kind === "purge" && <path d="M10 2l1.9 5 5.1-1.7-3 4.7 3 4.7-5.1-1.7L10 18l-1.9-5-5.1 1.7 3-4.7-3-4.7 5.1 1.7Z" />}
      {kind === "flow" && (
        <>
          <path d="M15.6 7.4A6 6 0 0 0 4.6 7M4.4 12.6A6 6 0 0 0 15.4 13" />
          <path d="M4.2 3.6v3.6h3.6M15.8 16.4v-3.6h-3.6" />
        </>
      )}
      {kind === "control" && (
        // a branch: one line splitting in two
        <path d="M6 2.5v15M6 7.5c0 3 8 2 8 5.5v4.5M14 17.5l-2.4-2.4M14 17.5l2.4-2.4" />
      )}
      {kind === "module" && (
        <>
          <rect x="5" y="5" width="10" height="10" rx="1.5" />
          <path d="M8 2v3M12 2v3M8 15v3M12 15v3M2 8h3M2 12h3M15 8h3M15 12h3" />
        </>
      )}
    </svg>
  );
}

// `readout`: the number in play right now (the hovered slot's, or the
// weakest free slot's) and the best one any free slot would give.
export interface Readout {
  value: number;
  best: number;
  // the value comes from a slot that beats the weakest one (an amplifier)
  boosted?: boolean;
}

// The smallest name and effect text a card face shrinks to (px) - a text
// that doesn't fit at these has to get shorter instead.
const NAME_FLOOR = 8;
const BODY_FLOOR = 11;

// Steps `el`'s font size down from its stylesheet size until `overflows`
// says it fits, or the floor is reached.
function shrinkToFit(el: HTMLElement, overflows: () => boolean, floor: number) {
  el.style.fontSize = "";
  let size = parseFloat(getComputedStyle(el).fontSize);
  while (size > floor && overflows()) {
    size = Math.max(floor, size - 0.5);
    el.style.fontSize = `${size}px`;
  }
}

// Whether a box's text runs wider or lower than the box (a long word does -
// it can't wrap; scrollWidth misses one that only runs into the padding),
// over more than `maxLines` lines, or - `besideFloat` - not all beside the
// box's ::before float (the name beside its socket, see App.css).
function textOverflows(el: HTMLElement, maxLines: number, besideFloat = false): boolean {
  const range = document.createRange();
  range.selectNodeContents(el);
  const rects = [...range.getClientRects()].filter((r) => r.width > 0);
  const style = getComputedStyle(el);
  const box = el.getBoundingClientRect();
  let left = box.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft);
  const right = box.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight);
  const bottom = box.bottom - parseFloat(style.borderBottomWidth) - parseFloat(style.paddingBottom);
  if (besideFloat) left += parseFloat(getComputedStyle(el, "::before").width) || 0;
  const lines = new Set(rects.map((r) => Math.round(r.top))).size;
  return lines > maxLines || rects.some((r) => r.left < left - 0.5 || r.right > right || r.bottom > bottom + 1);
}

// A long word with soft hyphens between two consonants that stand between
// vowels, unless they belong together ("Ran-som-ware", "Encryp-tion", but
// "Phishing"): the last resort for a word too long even at the floor size
// (the header's hyphens are off until then).
const VOWEL = /[aeiouy]/i;
const BLEND = /^(?:[bcdfgkpt][lr]|[cpstw]h|ck|qu)$/i;

function softHyphens(name: string): string {
  return name.replace(/[A-Za-z]{8,}/g, (word) => {
    let out = word[0];
    for (let i = 1; i < word.length; i++) {
      const split =
        i >= 3 &&
        i <= word.length - 3 &&
        VOWEL.test(word[i - 2]) &&
        !VOWEL.test(word[i - 1]) &&
        !VOWEL.test(word[i]) &&
        VOWEL.test(word[i + 1]) &&
        !BLEND.test(word[i - 1] + word[i]);
      out += (split ? "\u00ad" : "") + word[i];
    }
    return out;
  });
}

// Card faces come in many sizes (hand, slots, rewards, previews), so the name
// and the effect text are fitted to the card they are on: the name to its
// width in at most two lines (never cut off), the effect to the room under
// it. Measured, not guessed, since Orbitron's letters differ a lot in width.
function useFitText(key: string) {
  const header = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const name = header.current;
    const text = body.current;
    const card = name?.parentElement;
    if (!name || !text || !card) return;
    const fit = () => {
      // a card folding out of the hand (its width animating to 0, see
      // .is-played) isn't refitted on every frame
      if (card.clientWidth < 30 || card.classList.contains("is-played")) return;
      // a slot too small for the effect text shows only the name, under
      // the socket (see App.css), which may then take a third line
      const compact = getComputedStyle(text).display === "none";
      const maxLines = compact ? 3 : 2;
      // beside the socket if the name fits there at all, else (a word too
      // long even at the floor) flowing under it, at the card's full width
      name.style.hyphens = "";
      if (!compact) shrinkToFit(name, () => textOverflows(name, maxLines, true), NAME_FLOOR);
      if (compact || textOverflows(name, maxLines, true)) {
        shrinkToFit(name, () => textOverflows(name, maxLines), NAME_FLOOR);
        if (textOverflows(name, maxLines)) {
          name.style.hyphens = "manual";
          shrinkToFit(name, () => textOverflows(name, maxLines), NAME_FLOOR);
        }
      }
      const inner = text.firstElementChild as HTMLElement | null;
      if (!inner || compact) return;
      const style = getComputedStyle(text);
      const room = () => text.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
      shrinkToFit(text, () => inner.getBoundingClientRect().height > room() + 0.5, BODY_FLOOR);
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(card);
    // the web fonts may arrive after the first fit, and change every width
    document.fonts?.addEventListener("loadingdone", fit);
    // a card dealt, flipped or popped in (rewards, shop, a window opening)
    // is measured while it is still turned or scaled, which reads every line
    // as too wide - fit it again once an animation on it or any box around
    // it is over
    const settle = (event: AnimationEvent) => {
      if (event.target instanceof Node && event.target.contains(card)) fit();
    };
    document.addEventListener("animationend", settle, true);
    return () => {
      observer.disconnect();
      document.fonts?.removeEventListener("loadingdone", fit);
      document.removeEventListener("animationend", settle, true);
    };
  }, [key]);
  return { headerRef: header, bodyRef: body };
}

// `after` word by word against `before` (an upgrade against the card it
// was): the new words marked, and a number they replace shown struck out in
// front of them ("Gain 5 → 8 block"). Other words it drops are left out.
function changedText(before: string, after: string): ReactNode[] {
  const a = before.split(/(\s+)/);
  const b = after.split(/(\s+)/);
  // common[i][j]: the longest run of words a[i..] and b[j..] have in common
  const common = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
  const parts: ReactNode[] = [];
  let same = "";
  let dropped: string[] = [];
  let added: string[] = [];
  const flush = () => {
    if (same) parts.push(<RichText key={parts.length} text={same} focusable={false} />);
    same = "";
    const numbers = dropped.filter((word) => /\d/.test(word));
    if (numbers.length && added.length) parts.push(<del key={parts.length}>{numbers.join(" ")}</del>, " → ");
    const text = added.join("");
    if (text.trim())
      parts.push(
        <mark key={parts.length} className="card-changed">
          <RichText text={text} focusable={false} />
        </mark>,
      );
    else same = text;
    dropped = [];
    added = [];
  };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      if (dropped.length || added.length) flush();
      same += b[j];
      i++;
      j++;
    } else if (j < b.length && (i === a.length || common[i][j + 1] >= common[i + 1][j])) {
      added.push(b[j++]);
    } else {
      dropped.push(a[i++]);
    }
  }
  flush();
  if (same) parts.push(<RichText key={parts.length} text={same} focusable={false} />);
  return parts;
}

// on the field the module icon already says "permanent" (or "control
// flow"), so the effect text drops that prefix and keeps the room for what
// the card does; the same goes for one-shot cards and their "1×" tag.
// `changedFrom`: the card this one was before an upgrade - what the upgrade
// changes is highlighted (see changedText).
export function CardFace({
  card,
  onField = false,
  readout,
  changedFrom,
}: {
  card: Card;
  onField?: boolean;
  readout?: Readout;
  changedFrom?: Card;
}) {
  const showTokens = useContext(ShowTokensContext);
  // the type line (or, on the field, the module icon) says what kind of
  // card it is - the effect text starts with what it does
  const strip = (text: string) => text.replace(/^(Permanent|One-shot|Control flow)\.\s*/, "");
  const description = strip(useCardText(card));
  const before = strip(useCardText(changedFrom ?? card));
  const unit = unitOf(card.type);
  const line = typeLine(card, useContext(ProgramModeContext));
  // Prefetch draws every 2nd turn, Prefetch+ every turn (combat.cards_per_turn)
  const base = STAT[card.type];
  const stat = base && card.type === "draw_bonus" && !card.upgraded ? { ...base, unit: "every 2nd turn" } : base;
  const { headerRef, bodyRef } = useFitText(
    `${card.name}|${description}|${readout ? 1 : 0}|${showTokens}|${changedFrom ? before : ""}`,
  );
  // what the name gained (an upgrade's "+")
  const suffix = changedFrom && card.name.startsWith(changedFrom.name) ? card.name.slice(changedFrom.name.length) : "";
  return (
    <>
      {/* on the field a slot may be too small for the effect text: the
          name then tells it on hover */}
      <div ref={headerRef} className="card-header" title={onField ? `${card.name}: ${description}` : undefined}>
        {softHyphens(card.name.slice(0, card.name.length - suffix.length))}
        {suffix && <mark className="card-changed">{suffix}</mark>}
      </div>
      <span className="card-socket" title={KIND_LABEL[kindOf(card.type)]}>
        <CardTypeIcon type={card.type} />
      </span>
      {card.exhaust && (
        <span className="card-tag" data-keyword="one-shot">
          1×
        </span>
      )}
      {!onField && (
        <div
          className={`card-typeline${line.instant ? " is-instant" : ""}`}
          title={
            line.repeats
              ? "Stays on the field and works every turn"
              : line.instant
                ? "Takes effect the moment you play it - it never goes into a program line"
                : undefined
          }
        >
          {line.instant && (
            <svg viewBox="0 0 20 20" aria-hidden="true" className="card-typeline-icon is-bolt">
              <path d="M11.5 1.5 4 11h5l-1.5 7.5L16 9h-5.2Z" />
            </svg>
          )}
          {line.repeats && (
            <svg viewBox="0 0 20 20" aria-hidden="true" className="card-typeline-icon">
              <path d="M15.6 7.4A6 6 0 0 0 4.6 7M4.4 12.6A6 6 0 0 0 15.4 13" />
              <path d="M4.2 3.6v3.6h3.6M15.8 16.4v-3.6h-3.6" />
            </svg>
          )}
          <b>{line.label}</b>
        </div>
      )}
      {/* the number the card comes out with: in a fight its real value
          (ATK and the slot included), elsewhere its own */}
      {!onField && unit && (readout || card.value > 0) && (
        <div className={`card-readout${readout?.boosted ? " is-boosted" : ""}${readout ? "" : " is-base"}`}>
          <span className="card-readout-icon">
            <CardTypeIcon type={card.type} />
          </span>
          <b>
            {card.hits > 1 && <small>{card.hits}×</small>}
            {readout ? readout.value : card.value}
          </b>
          <span className="card-unit">{unit}</span>
          {readout && readout.best > readout.value && <span className="card-best">max {readout.best}</span>}
        </div>
      )}
      {!onField && !unit && stat && card.value > 0 && (
        <div className="card-readout card-stat">
          <StatGlyph icon={stat.icon} />
          <b>
            {stat.sign ?? ""}
            {stat.half ? card.value / 2 : card.value}
            {stat.percent ? "%" : ""}
          </b>
          <span className="card-unit">{stat.unit}</span>
        </div>
      )}
      {/* what is left of the effect where a narrow slot hides the text */}
      {onField && unit && card.value > 0 && (
        <span className="card-mini">
          {card.hits > 1 && `${card.hits}×`}
          {card.value} <small>{unit}</small>
        </span>
      )}
      <div ref={bodyRef} className="card-body">
        {/* one inline box: the body is a flex container, the terms must not become items */}
        <span>
          {changedFrom ? changedText(before, description) : <RichText text={description} focusable={false} />}
        </span>
      </div>
      {showTokens && !onField && (
        <span
          className={`card-tokens${changedFrom && changedFrom.token_cost !== card.token_cost ? " is-changed" : ""}`}
          title={`Costs ${card.token_cost} token(s) of context`}
        >
          {card.token_cost}
          <small>tok</small>
        </span>
      )}
      {card.rarity !== "starter" && <span className={`card-gem rarity-${card.rarity}`} />}
      {/* a permanent is built like a chip - contacts down both sides - so it
          reads apart from the one-time cards at a glance (see faces.css) */}
      {!onField && PERMANENT_CARD_TYPES.includes(card.type) && <span className="card-pins" aria-hidden="true" />}
      {/* the card's "art": its type glyph, large and faint behind the text */}
      {!onField && (
        <span className="card-watermark" aria-hidden="true">
          <CardTypeIcon type={card.type} />
        </span>
      )}
      {/* its rarity on its edge: silver for uncommon, gold with corner marks for rare
          (alive.css; the foil below is its shine), and a tag at its foot */}
      {!onField && (card.rarity === "uncommon" || card.rarity === "rare") && (
        <span className={`card-edge is-${card.rarity}`} aria-hidden="true" />
      )}
      {!onField && card.rarity === "rare" && <span className="card-corners" aria-hidden="true" />}
      {!onField && <span className={`card-rarity is-${card.rarity}`}>{card.rarity}</span>}
      {/* a rare card's foil, which catches the light as the card tilts (tilt.ts) */}
      {card.rarity === "rare" && !onField && <span className="card-foil" aria-hidden="true" />}
    </>
  );
}
