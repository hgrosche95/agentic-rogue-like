import { useEffect, useState } from "react";
import type { Card, ShopView } from "../api";
import { sfx } from "../audio";
import { ArtifactIcon } from "./ArtifactIcon";
import { CardFace } from "./CardFace";

function PriceTag({ price, sold, affordable }: { price: number; sold: boolean; affordable: boolean }) {
  return (
    <span className={`price-tag${sold ? " is-sold" : affordable ? "" : " is-short"}`}>
      {sold ? "Sold" : `${price} cr`}
    </span>
  );
}

// The black market: a random pick of cards and artifacts for credits, and
// one card removal. Buy as many as the credits allow, then leave - the run
// moves on from there.
export function ShopScreen({
  shop,
  gold,
  deck,
  disabled,
  onBuyCard,
  onBuyArtifact,
  onRemoveCard,
  onLeave,
}: {
  shop: ShopView;
  gold: number;
  deck: Card[];
  disabled: boolean;
  onBuyCard: (index: number) => void;
  onBuyArtifact: (index: number) => void;
  onRemoveCard: (deckIndex: number) => void;
  onLeave: () => void;
}) {
  const [purging, setPurging] = useState(false);
  const deckTooSmall = deck.length <= shop.min_deck_size;
  const canPurge = !shop.removal_used && gold >= shop.removal_price && !deckTooSmall;
  const purgeNote = shop.removal_used
    ? "Done - one purge per black market."
    : deckTooSmall
      ? `Your deck can't get smaller than ${shop.min_deck_size} cards.`
      : gold < shop.removal_price
        ? "Not enough credits."
        : "Remove one card from your deck for good. Every purge costs more.";

  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  return (
    <div className="reward-screen shop-screen">
      <h2>Black market</h2>
      <p className="reward-hint">
        You have <b className="shop-credits">{gold} credits</b>. Buy what you can afford, then move on.
      </p>

      <h3 className="shop-section">Cards</h3>
      <div className="reward-cards shop-cards">
        {shop.cards.map(({ card, price, sold }, index) => {
          const affordable = gold >= price;
          return (
            <div key={card.id} className="shop-item">
              <button
                className={`hand-card reward-card type-${card.type} rarity-${card.rarity}${sold ? " is-sold" : ""}`}
                style={{ animationDelay: `${index * 90}ms` }}
                disabled={disabled || sold || !affordable}
                aria-label={`Buy ${card.name} for ${price} credits`}
                onMouseEnter={() => sfx.play("hover")}
                onClick={() => {
                  sfx.play("reward_pick");
                  onBuyCard(index);
                }}
              >
                <CardFace card={card} />
              </button>
              <PriceTag price={price} sold={sold} affordable={affordable} />
            </div>
          );
        })}
      </div>

      <h3 className="shop-section">Artifacts</h3>
      <div className="artifact-offer shop-artifacts">
        {shop.artifacts.map(({ artifact, price, sold }, index) => {
          const affordable = gold >= price;
          return (
            <div key={artifact.id} className="shop-item">
              <button
                className={`artifact-card${sold ? " is-sold" : ""}`}
                style={{ animationDelay: `${(index + 4) * 90}ms` }}
                disabled={disabled || sold || !affordable}
                aria-label={`Buy ${artifact.name} for ${price} credits`}
                onMouseEnter={() => sfx.play("hover")}
                onClick={() => {
                  sfx.play("reward_pick");
                  onBuyArtifact(index);
                }}
              >
                <span className="artifact-badge is-large">
                  <ArtifactIcon id={artifact.id} size={30} />
                </span>
                <span className="artifact-name">{artifact.name}</span>
                <span className="artifact-description">{artifact.description}</span>
              </button>
              <PriceTag price={price} sold={sold} affordable={affordable} />
            </div>
          );
        })}
      </div>

      <h3 className="shop-section">Purge a card</h3>
      <div className="shop-purge">
        <PriceTag price={shop.removal_price} sold={shop.removal_used} affordable={gold >= shop.removal_price} />
        <span className="shop-purge-note">{purgeNote}</span>
        {canPurge && (
          <button
            type="button"
            className="shop-purge-toggle"
            disabled={disabled}
            onClick={() => {
              sfx.play("click");
              setPurging((p) => !p);
            }}
          >
            {purging ? "Cancel" : "Choose a card"}
          </button>
        )}
      </div>
      {canPurge && purging && (
        <div className="deck-grid shop-purge-grid">
          {deck.map((card, index) => (
            <button
              key={card.id}
              type="button"
              className={`hand-card deck-card type-${card.type}`}
              disabled={disabled}
              aria-label={`Purge ${card.name} for ${shop.removal_price} credits`}
              onMouseEnter={() => sfx.play("hover")}
              onClick={() => {
                sfx.play("reward_pick");
                setPurging(false);
                onRemoveCard(index);
              }}
            >
              <CardFace card={card} />
            </button>
          ))}
        </div>
      )}

      <button
        className="reward-skip"
        disabled={disabled}
        onClick={() => {
          sfx.play("click");
          onLeave();
        }}
      >
        Leave
      </button>
    </div>
  );
}
