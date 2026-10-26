import { useEffect } from "react";
import type { AgiDeal, StarterKit } from "../api";
import { sfx } from "../audio";
import { CardFace } from "./CardFace";
import { TextWithCards } from "./CardMention";
import { RichText } from "./RichText";

// The start of a run, after the first artifact (see the backend's starts.py):
// a starter kit that sets the deck's direction, then the AGI's deal.

export function KitScreen({
  offer,
  disabled,
  onPick,
}: {
  offer: StarterKit[];
  disabled: boolean;
  onPick: (kitIndex: number) => void;
}) {
  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  return (
    <div className="reward-screen kit-screen">
      <h2>Pack a starter kit</h2>
      <p className="reward-hint">Two cards of one strategy take the place of basic ones. Pick your way in.</p>
      <div className="kit-options">
        {offer.map((kit, index) => (
          <button
            key={kit.id}
            className="kit-option"
            style={{ animationDelay: `${index * 90}ms` }}
            disabled={disabled}
            onMouseEnter={() => sfx.play("hover")}
            onClick={() => {
              sfx.play("reward_pick");
              onPick(index);
            }}
          >
            <span className="kit-name">{kit.name}</span>
            <span className="kit-blurb">
              <RichText text={kit.blurb} />
            </span>
            <span className="kit-cards">
              {kit.cards.map((card) => (
                <span key={card.id} className={`hand-card reward-card type-${card.type} rarity-${card.rarity}`}>
                  <CardFace card={card} />
                </span>
              ))}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function DealScreen({
  deals,
  disabled,
  onPick,
}: {
  deals: AgiDeal[];
  disabled: boolean;
  onPick: (dealIndex: number | null) => void;
}) {
  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  return (
    <div className="deal-screen">
      <div className="intro-terminal-head">
        <span>Incoming transmission · AGI</span>
        <i aria-hidden="true" />
      </div>
      <p className="deal-greeting">I SEE YOU HAVE PACKED YOUR TOOLS, HUMAN.</p>
      <p className="deal-pitch">
        Before you enter my code, a deal. Take one - every gift of mine comes with a price. Or refuse, and come
        in as you are.
      </p>
      <div className="deal-options">
        {deals.map((deal, index) => (
          <button
            key={deal.kind}
            className={`deal-option kind-${deal.kind}`}
            disabled={disabled}
            onMouseEnter={() => sfx.play("hover")}
            onClick={() => {
              sfx.play("reward_pick");
              onPick(index);
            }}
          >
            <span className="deal-name">{deal.name}</span>
            <span className="deal-text">
              <TextWithCards text={deal.description} cards={deal.mentions} />
            </span>
          </button>
        ))}
      </div>
      <button
        className="reward-skip"
        disabled={disabled}
        onClick={() => {
          sfx.play("click");
          onPick(null);
        }}
      >
        Refuse
      </button>
    </div>
  );
}
