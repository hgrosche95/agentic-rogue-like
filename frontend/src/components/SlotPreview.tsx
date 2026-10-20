import type { HandCardView } from "../api";
import { unitOf } from "../readouts";

// An empty slot shows its number - and, while a card is aimed at the stack,
// what that card would do from here, lit up where an amplifier boosts it.
export function SlotPreview({ index, card, low }: { index: number; card?: HandCardView; low?: number }) {
  const label = String(index + 1).padStart(2, "0");
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
