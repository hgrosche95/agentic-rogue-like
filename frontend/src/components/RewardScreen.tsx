import { useEffect, type CSSProperties } from "react";
import type { Card } from "../api";
import { sfx } from "../audio";
import { pickClass, useOverlayPick } from "../overlayStage";
import { CardFace } from "./CardFace";

// The cards are dealt face down and turned over one after another (the
// timings match .reward-slot in neon.css): each flip is heard as it passes
// edge-on, and a rare card shines as it comes up.
const FLIP_START_MS = 380;
const FLIP_STAGGER_MS = 230;
const FLIP_MS = 560;

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

  const rarities = offer.map((card) => card.rarity).join(" ");
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const timers = rarities.split(" ").map((rarity, index) =>
      window.setTimeout(
        () => {
          sfx.play("card_flip");
          if (rarity === "rare") sfx.play("rare_reveal", { delayMs: 120 });
        },
        FLIP_START_MS + index * FLIP_STAGGER_MS + FLIP_MS / 2,
      ),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [rarities]);

  return (
    <div className="reward-screen">
      <h2>Choose a card</h2>
      <p className="reward-hint">Add one to your deck ({deckSize} cards) - or skip to keep it lean.</p>
      <div className="reward-cards">
        {offer.map((card, index) => (
          <div key={card.id} className="reward-slot" style={{ "--i": index } as CSSProperties}>
            <button
              className={`hand-card reward-card type-${card.type} rarity-${card.rarity}${pickClass(picked, index)}`}
              disabled={disabled}
              onMouseEnter={() => sfx.play("hover")}
              onClick={() => {
                sfx.play("reward_pick");
                pick(index);
                onPick(index);
              }}
            >
              <CardFace card={card} />
              <span className="reward-card-back" aria-hidden="true" />
              {card.rarity === "rare" && <span className="reward-card-shine" aria-hidden="true" />}
            </button>
            {card.rarity === "rare" && <span className="reward-glow" aria-hidden="true" />}
          </div>
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
