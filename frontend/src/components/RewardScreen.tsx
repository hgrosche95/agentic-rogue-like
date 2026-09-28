import type { Card } from "../api";
import { CardFace } from "./CardFace";

export function RewardScreen({
  offer,
  deckSize,
  disabled,
  onPick,
}: {
  offer: Card[];
  deckSize: number;
  disabled: boolean;
  onPick: (cardIndex: number | null) => void;
}) {
  return (
    <div className="reward-screen">
      <h2>Choose a card</h2>
      <p className="reward-hint">
        Add one to your deck ({deckSize} cards) - or skip to keep it lean.
      </p>
      <div className="reward-cards">
        {offer.map((card, index) => (
          <button
            key={card.id}
            className={`hand-card reward-card type-${card.type} rarity-${card.rarity}`}
            style={{ animationDelay: `${index * 220}ms` }}
            disabled={disabled}
            onClick={() => onPick(index)}
          >
            <CardFace card={card} />
          </button>
        ))}
      </div>
      <button className="reward-skip" disabled={disabled} onClick={() => onPick(null)}>
        Skip
      </button>
    </div>
  );
}
