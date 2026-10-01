import { useEffect } from "react";
import type { Card } from "../api";
import { sfx } from "../audio";
import { CardFace } from "./CardFace";

export function RewardScreen({
  offer,
  deckSize,
  disabled,
  onPick,
  isStart = false,
}: {
  offer: Card[];
  deckSize: number;
  disabled: boolean;
  onPick: (cardIndex: number | null) => void;
  // the pick of uncommon/rare cards before the first room
  isStart?: boolean;
}) {
  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  return (
    <div className="reward-screen">
      <h2>{isStart ? "Choose a starting card" : "Choose a card"}</h2>
      <p className="reward-hint">
        {isStart
          ? `Pack one uncommon or rare card into your starter deck (${deckSize} cards) before you jump - or skip.`
          : `Add one to your deck (${deckSize} cards) - or skip to keep it lean.`}
      </p>
      <div className="reward-cards">
        {offer.map((card, index) => (
          <button
            key={card.id}
            className={`hand-card reward-card type-${card.type} rarity-${card.rarity}`}
            style={{ animationDelay: `${index * 90}ms` }}
            disabled={disabled}
            onMouseEnter={() => sfx.play("hover")}
            onClick={() => {
              sfx.play("reward_pick");
              onPick(index);
            }}
          >
            <CardFace card={card} />
          </button>
        ))}
      </div>
      <button className="reward-skip" disabled={disabled} onClick={() => {
          sfx.play("click");
          onPick(null);
        }}>
        Skip
      </button>
    </div>
  );
}
