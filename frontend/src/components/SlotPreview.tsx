import { PERMANENT_CARD_TYPES, type HandCardView } from "../api";
import { unitOf } from "../readouts";

// An empty slot shows its number - and, while a card is aimed at the stack,
// what that card would do from here, lit up where an amplifier boosts it.
// `slots` (the classic field's size): a permanent aimed at it shows what it
// does from here instead - an Overclock or a Copilot how many slots to its
// right it boosts, any other one that it works every turn.
export function SlotPreview({
  index,
  card,
  low,
  slots,
}: {
  index: number;
  card?: HandCardView;
  low?: number;
  slots?: number;
}) {
  const label = String(index + 1).padStart(2, "0");
  if (card && slots !== undefined && PERMANENT_CARD_TYPES.includes(card.type)) {
    const boosts = card.type === "amplifier" || card.type === "chain";
    const right = slots - 1 - index;
    return (
      <span className={`slot-preview is-permanent${boosts && right > 0 ? " is-boosted" : ""}`}>
        <span className="slot-no">{label}</span>
        <b>{boosts ? `${right}→` : "↻"}</b>
        <span className="slot-unit">{boosts ? (right === 1 ? "slot boosted" : "slots boosted") : "every turn"}</span>
      </span>
    );
  }
  const value = card?.preview[index];
  const unit = card && unitOf(card.type);
  if (value === null || value === undefined || !unit) return <>{label}</>;
  return (
    <span className={`slot-preview${low !== undefined && value > low ? " is-boosted" : ""}`}>
      <span className="slot-no">{label}</span>
      <b>{value}</b>
      <span className="slot-unit">{unit}</span>
    </span>
  );
}
