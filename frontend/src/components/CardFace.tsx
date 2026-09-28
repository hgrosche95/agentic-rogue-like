import { PERMANENT_CARD_TYPES, type Card } from "../api";

// on the field the ∞ badge already says "permanent", so the effect text
// drops that prefix and keeps the room for what the card does; the same
// goes for one-shot cards and their "1×" tag
export function CardFace({ card, onField = false }: { card: Card; onField?: boolean }) {
  const isPermanent = PERMANENT_CARD_TYPES.includes(card.type);
  const description = card.description.replace(
    onField ? /^(Permanent|One-shot)\.\s*/ : /^One-shot\.\s*/,
    "",
  );
  return (
    <>
      <div className="card-header">{card.name}</div>
      <span className="card-rank">{isPermanent ? "∞" : card.value}</span>
      {card.exhaust && (
        <span className="card-tag" title="One-shot: banished after use">
          1×
        </span>
      )}
      <div className="card-body">{description}</div>
      {card.rarity !== "starter" && <span className={`card-gem rarity-${card.rarity}`} />}
    </>
  );
}
