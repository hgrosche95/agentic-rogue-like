import { useEffect, useState } from "react";
import type { Card, RestUpgrade, RestView } from "../api";
import { sfx } from "../audio";
import { CardFace } from "./CardFace";

type Mode = "choose" | "upgrade" | "remove";

// What an upgrade changes, short: its main number, its hit count or its
// scaling bonus - today's text only for anything else.
function changeOf({ card, upgraded }: RestUpgrade): string {
  const unit = card.type === "amplifier" ? "%" : "";
  if (upgraded.value !== card.value) return `${card.value}${unit} → ${upgraded.value}${unit}`;
  if (upgraded.hits !== card.hits) return `${card.hits}× → ${upgraded.hits}×`;
  if (upgraded.scale_value !== card.scale_value) return `+${card.scale_value} → +${upgraded.scale_value} each`;
  if (upgraded.token_cost !== card.token_cost) return `${card.token_cost} → ${upgraded.token_cost} tokens`;
  return `now: ${card.description}`;
}

// Identical cards (same name, so same upgrade state) as one tile with a
// count, like the deck view - picking it acts on the first copy.
function stacked<T>(items: T[], card: (item: T) => Card): { item: T; count: number }[] {
  const stacks = new Map<string, { item: T; count: number }>();
  for (const item of items) {
    const stack = stacks.get(card(item).name);
    if (stack) stack.count += 1;
    else stacks.set(card(item).name, { item, count: 1 });
  }
  return [...stacks.values()];
}

// A safehouse between jumps: patch yourself up, rework one card for good,
// or strip one out of the deck - one of the three, then the run moves on.
export function RestScreen({
  rest,
  hp,
  maxHp,
  deck,
  disabled,
  onHeal,
  onUpgrade,
  onRemove,
}: {
  rest: RestView;
  hp: number;
  maxHp: number;
  deck: Card[];
  disabled: boolean;
  onHeal: () => void;
  onUpgrade: (deckIndex: number) => void;
  onRemove: (deckIndex: number) => void;
}) {
  const [mode, setMode] = useState<Mode>("choose");
  const healed = Math.min(maxHp, hp + rest.heal_amount);

  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  const pick = (next: Mode) => {
    sfx.play("click");
    setMode(next);
  };

  return (
    <div className="reward-screen rest-screen">
      <h2>Safehouse</h2>

      {mode === "choose" && (
        <>
          <p className="reward-hint">Choose one - then the timeline pulls you onward.</p>
          <div className="artifact-offer rest-options">
            <button
              type="button"
              className="artifact-card rest-option"
              disabled={disabled}
              onMouseEnter={() => sfx.play("hover")}
              onClick={() => {
                sfx.play("heal");
                onHeal();
              }}
            >
              <span className="artifact-name">Rest</span>
              <span className="rest-figure">+{rest.heal_amount} HP</span>
              <span className="artifact-description">
                Patch yourself up: {hp} → {healed} of {maxHp} integrity.
              </span>
            </button>
            <button
              type="button"
              className="artifact-card rest-option"
              disabled={disabled || rest.upgrades.length === 0}
              onMouseEnter={() => sfx.play("hover")}
              onClick={() => pick("upgrade")}
            >
              <span className="artifact-name">Rework</span>
              <span className="rest-figure">+ one card</span>
              <span className="artifact-description">
                {rest.upgrades.length
                  ? "Upgrade a card for the rest of the run."
                  : "Nothing left to upgrade."}
              </span>
            </button>
            <button
              type="button"
              className="artifact-card rest-option"
              disabled={disabled || !rest.can_remove}
              onMouseEnter={() => sfx.play("hover")}
              onClick={() => pick("remove")}
            >
              <span className="artifact-name">Strip out</span>
              <span className="rest-figure">− one card</span>
              <span className="artifact-description">
                {rest.can_remove
                  ? "Remove a card from your deck for free."
                  : `Your deck can't get smaller than ${rest.min_deck_size} cards.`}
              </span>
            </button>
          </div>
        </>
      )}

      {mode === "upgrade" && (
        <>
          <p className="reward-hint">Pick a card to rework - this is how it will read from now on.</p>
          <div className="deck-grid rest-grid">
            {stacked<RestUpgrade>(rest.upgrades, (u) => u.card).map(({ item, count }) => (
              <div key={item.card.id} className="rest-pick">
                <button
                  type="button"
                  className={`hand-card deck-card type-${item.upgraded.type}`}
                  disabled={disabled}
                  aria-label={`Upgrade ${item.card.name} to ${item.upgraded.name}`}
                  onMouseEnter={() => sfx.play("hover")}
                  onClick={() => {
                    sfx.play("reward_pick");
                    onUpgrade(item.deck_index);
                  }}
                >
                  <CardFace card={item.upgraded} />
                  {count > 1 && <span className="deck-count">×{count}</span>}
                </button>
                <span className="rest-before" title={`Now: ${item.card.description}`}>
                  {changeOf(item)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {mode === "remove" && (
        <>
          <p className="reward-hint">Pick a card to remove from your deck for good.</p>
          <div className="deck-grid rest-grid">
            {stacked(
              deck.map((card, index) => ({ card, index })),
              (entry) => entry.card,
            ).map(({ item: { card, index }, count }) => (
              <button
                key={card.id}
                type="button"
                className={`hand-card deck-card type-${card.type}`}
                disabled={disabled}
                aria-label={`Remove ${card.name}`}
                onMouseEnter={() => sfx.play("hover")}
                onClick={() => {
                  sfx.play("reward_pick");
                  onRemove(index);
                }}
              >
                <CardFace card={card} />
                {count > 1 && <span className="deck-count">×{count}</span>}
              </button>
            ))}
          </div>
        </>
      )}

      {mode !== "choose" && (
        <button type="button" className="reward-skip" disabled={disabled} onClick={() => pick("choose")}>
          Back
        </button>
      )}
    </div>
  );
}
