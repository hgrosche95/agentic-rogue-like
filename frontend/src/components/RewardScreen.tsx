import { useEffect } from "react";
import type { Card } from "../api";
import { sfx } from "../audio";
import { pickClass, useOverlayPick } from "../overlayStage";
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
  const { picked, pick } = useOverlayPick();
  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  return (
    <div className="reward-screen">
      <h2>Choose a card</h2>
      <p className="reward-hint">Add one to your deck ({deckSize} cards) - or skip to keep it lean.</p>
      <div className="reward-cards">
        {offer.map((card, index) => (
          <button
            key={card.id}
            className={`hand-card reward-card type-${card.type} rarity-${card.rarity}${pickClass(picked, index)}`}
            style={{ animationDelay: `${index * 90}ms` }}
            disabled={disabled}
            onMouseEnter={() => sfx.play("hover")}
            onClick={() => {
              sfx.play("reward_pick");
              pick(index);
              onPick(index);
            }}
          >
            <CardFace card={card} />
          </button>
        ))}
      </div>
      <button
        className={`reward-skip${pickClass(picked, "skip")}`}
        disabled={disabled}
        onClick={() => {
          sfx.play("click");
          pick("skip");
          onPick(null);
        }}
      >
        Skip
      </button>
    </div>
  );
}
