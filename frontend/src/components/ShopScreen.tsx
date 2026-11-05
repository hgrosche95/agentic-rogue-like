import { useEffect, useState } from "react";
import type { Card, ShopView } from "../api";
import { sfx } from "../audio";
import { pickClass, useOverlayPick } from "../overlayStage";
import { flyInto } from "../cardFlight";
import { ArtifactIcon } from "./ArtifactIcon";
import { CardFace } from "./CardFace";
import { RichText } from "./RichText";

function PriceTag({ price, sold, affordable }: { price: number; sold: boolean; affordable: boolean }) {
  return (
    <span className={`price-tag${sold ? " is-sold" : affordable ? "" : " is-short"}`}>
      {sold ? (
        "Sold"
      ) : (
        <>
          <svg className="price-coin" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M6 1 10.3 3.5v5L6 11 1.7 8.5v-5Z" />
            <path d="M7.6 4.6A2 2 0 1 0 7.6 7.4" />
          </svg>
          {price}
          <small>cr</small>
        </>
      )}
    </span>
  );
}

// The black market: a random pick of cards and artifacts for credits, and
// one card removal. Buy as many as the credits allow, then leave - the run
// moves on from there.
// Not enough credits: the item shakes its head, and the credits flash.
function shake(el: HTMLElement): void {
  sfx.play("click");
  el.animate(
    [
      { transform: "translateX(0)" },
      { transform: "translateX(-6px)" },
      { transform: "translateX(5px)" },
      { transform: "translateX(-3px)" },
      { transform: "translateX(0)" },
    ],
    { duration: 320, easing: "ease-out" },
  );
  document
    .querySelector(".shop-credits")
    ?.animate([{ color: "#ff4f8b" }, { color: "#ff4f8b" }, { color: "" }], { duration: 700 });
}

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
  const { picked, pick } = useOverlayPick();
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
                className={`hand-card reward-card type-${card.type} rarity-${card.rarity}${sold ? " is-sold" : ""}${affordable ? "" : " is-unaffordable"}`}
                style={{ animationDelay: `${index * 90}ms` }}
                disabled={disabled || sold}
                aria-disabled={!affordable}
                aria-label={`Buy ${card.name} for ${price} credits${affordable ? "" : " - not enough credits"}`}
                onMouseEnter={() => sfx.play("hover")}
                onClick={(event) => {
                  if (!affordable) return shake(event.currentTarget);
                  sfx.play("reward_pick");
                  flyInto(event.currentTarget, document.querySelector<HTMLElement>(".deck-button"));
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
                className={`artifact-card${sold ? " is-sold" : ""}${affordable ? "" : " is-unaffordable"}`}
                style={{ animationDelay: `${(index + 4) * 90}ms` }}
                disabled={disabled || sold}
                aria-disabled={!affordable}
                aria-label={`Buy ${artifact.name} for ${price} credits${affordable ? "" : " - not enough credits"}`}
                onMouseEnter={() => sfx.play("hover")}
                onClick={(event) => {
                  if (!affordable) return shake(event.currentTarget);
                  sfx.play("reward_pick");
                  flyInto(
                    event.currentTarget.querySelector<HTMLElement>(".artifact-badge") ?? event.currentTarget,
                    document.querySelector<HTMLElement>(".artifact-shelf, .artifact-panel"),
                  );
                  onBuyArtifact(index);
                }}
              >
                <span className="artifact-badge is-large">
                  <ArtifactIcon id={artifact.id} size={30} />
                </span>
                <span className="artifact-name">{artifact.name}</span>
                <span className="artifact-description">
                  <RichText text={artifact.description} />
                </span>
              </button>
              <PriceTag price={price} sold={sold} affordable={affordable} />
            </div>
          );
        })}
      </div>

      <h3 className="shop-section">Delete a card</h3>
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
              aria-label={`Delete ${card.name} for ${shop.removal_price} credits`}
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
        className={`reward-skip${pickClass(picked, "leave")}`}
        disabled={disabled}
        onClick={() => {
          sfx.play("click");
          pick("leave");
          onLeave();
        }}
      >
        Leave
      </button>
    </div>
  );
}
