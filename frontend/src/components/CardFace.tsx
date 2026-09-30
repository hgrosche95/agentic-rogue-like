import { PERMANENT_CARD_TYPES, type Card, type CardType } from "../api";
import { unitOf } from "../readouts";

// Each card is a module: a drawn type icon in the socket top left (where
// other deckbuilders put a cost - this game has none), and, in combat, a
// readout with the number the card will really come out with.

type Kind = "strike" | "shield" | "repair" | "purge" | "flow" | "module";

function kindOf(type: CardType): Kind {
  if (PERMANENT_CARD_TYPES.includes(type)) return "module";
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
  purge: "Purge",
  flow: "Card flow",
  module: "Permanent",
};

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

// on the field the module icon already says "permanent", so the effect text
// drops that prefix and keeps the room for what the card does; the same
// goes for one-shot cards and their "1×" tag
export function CardFace({ card, onField = false, readout }: { card: Card; onField?: boolean; readout?: Readout }) {
  const description = card.description.replace(
    onField ? /^(Permanent|One-shot)\.\s*/ : /^One-shot\.\s*/,
    "",
  );
  const unit = unitOf(card.type);
  return (
    <>
      <div className="card-header">{card.name}</div>
      <span className="card-socket" title={KIND_LABEL[kindOf(card.type)]}>
        <CardTypeIcon type={card.type} />
      </span>
      {card.exhaust && (
        <span className="card-tag" title="One-shot: banished after use">
          1×
        </span>
      )}
      {readout && unit && (
        <div className={`card-readout${readout.boosted ? " is-boosted" : ""}`}>
          <b>
            {card.hits > 1 && <small>{card.hits}×</small>}
            {readout.value}
          </b>
          <span className="card-unit">{unit}</span>
          {readout.best > readout.value && <span className="card-best">max {readout.best}</span>}
        </div>
      )}
      <div className="card-body">{description}</div>
      {card.rarity !== "starter" && <span className={`card-gem rarity-${card.rarity}`} />}
    </>
  );
}
