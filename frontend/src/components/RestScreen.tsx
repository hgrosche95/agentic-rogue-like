import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { Card, RestUpgrade, RestView } from "../api";
import { sfx } from "../audio";
import { listDeck } from "../deck";
import { pickClass, useOverlayPick } from "../overlayStage";
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
  if (upgraded.applies_amount !== card.applies_amount)
    return `${card.applies_amount} → ${upgraded.applies_amount} ${card.applies}`;
  return `now: ${card.description}`;
}

// how long a touch has to rest on a card before it shows its upgrade, and
// how far it may wander meanwhile (scrolling the grid cancels it) - the same
// as for a term's tooltip (RichText)
const LONG_PRESS_MS = 450;
const LONG_PRESS_SLOP_PX = 8;

// Which deck card shows its upgrade: the one hovered or focused, or on touch
// the one long-pressed - a long press that shows it doesn't also pick it.
function useUpgradePreview() {
  const [shown, setShown] = useState<number | null>(null);
  const press = useRef<{ timer: number; x: number; y: number } | null>(null);
  const swallowClick = useRef(false);
  const cancelPress = () => {
    if (press.current) window.clearTimeout(press.current.timer);
    press.current = null;
  };
  useEffect(() => cancelPress, []);

  const hide = (index: number) => setShown((s) => (s === index ? null : s));
  const handlers = (index: number) => ({
    onPointerEnter: (event: PointerEvent) => event.pointerType !== "touch" && setShown(index),
    onPointerLeave: (event: PointerEvent) => event.pointerType !== "touch" && hide(index),
    onFocus: () => setShown(index),
    onBlur: () => hide(index),
    onPointerDown: (event: PointerEvent) => {
      cancelPress();
      swallowClick.current = false;
      if (event.pointerType !== "touch") return;
      press.current = {
        x: event.clientX,
        y: event.clientY,
        timer: window.setTimeout(() => {
          press.current = null;
          swallowClick.current = true;
          setShown(index);
        }, LONG_PRESS_MS),
      };
    },
    onPointerMove: (event: PointerEvent) => {
      const at = press.current;
      if (at && Math.hypot(event.clientX - at.x, event.clientY - at.y) > LONG_PRESS_SLOP_PX) cancelPress();
    },
    onPointerUp: cancelPress,
    onPointerCancel: cancelPress,
    // a long press opens no context menu either
    onContextMenu: (event: { preventDefault: () => void }) => {
      if (press.current || swallowClick.current) event.preventDefault();
    },
  });
  // whether a click only ends a long press
  const longPressed = () => {
    const was = swallowClick.current;
    swallowClick.current = false;
    return was;
  };
  return { shown, handlers, longPressed };
}

// A safehouse between jumps: patch yourself up, rework one card for good,
// or strip one out of the deck - one of the three, then the run moves on.
// Both picks list every copy of a card on its own, since each is its own
// card (an upgrade or removal acts on that one copy).
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
  const { picked, pick: pickChoice } = useOverlayPick();
  const preview = useUpgradePreview();
  const healed = Math.min(maxHp, hp + rest.heal_amount);
  const upgradeOf = new Map(rest.upgrades.map((u) => [u.deck_index, u]));
  // the cards that can be upgraded first, then the ones that can't
  const upgradeList = listDeck(deck).sort((a, b) => Number(!upgradeOf.has(a.index)) - Number(!upgradeOf.has(b.index)));

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
          <p className="reward-hint">Choose one - then the code pulls you deeper.</p>
          <div className="artifact-offer rest-options">
            <button
              type="button"
              className={`artifact-card rest-option${pickClass(picked, "heal")}`}
              disabled={disabled}
              onMouseEnter={() => sfx.play("hover")}
              onClick={() => {
                sfx.play("heal");
                pickChoice("heal");
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
          <p className="reward-hint">
            Pick a card to rework for good. Hover it (long-press on touch) to see how it will read.
          </p>
          <div className="deck-grid rest-grid">
            {upgradeList.map(({ card, index }) => {
              const upgrade = upgradeOf.get(index);
              const shown = upgrade && preview.shown === index;
              return (
                <div key={card.id} className="rest-pick">
                  <button
                    type="button"
                    className={`hand-card deck-card type-${card.type}${upgrade ? "" : " is-locked"}${shown ? " is-previewing" : ""}${pickClass(picked, index)}`}
                    disabled={disabled || !upgrade}
                    aria-label={
                      upgrade
                        ? `Upgrade ${card.name} to ${upgrade.upgraded.name}: ${upgrade.upgraded.description}`
                        : `${card.name} can't be upgraded`
                    }
                    onMouseEnter={() => sfx.play("hover")}
                    {...preview.handlers(index)}
                    onClick={() => {
                      if (preview.longPressed() || !upgrade) return;
                      sfx.play("reward_pick");
                      pickChoice(index);
                      onUpgrade(index);
                    }}
                  >
                    {shown ? <CardFace card={upgrade.upgraded} changedFrom={card} /> : <CardFace card={card} />}
                  </button>
                  <span
                    className={`rest-before${upgrade ? "" : " is-locked"}`}
                    title={upgrade ? `Upgraded: ${upgrade.upgraded.description}` : undefined}
                  >
                    {upgrade ? changeOf(upgrade) : card.upgraded ? "Already upgraded" : "Can't be upgraded"}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      {mode === "remove" && (
        <>
          <p className="reward-hint">Pick a card to remove from your deck for good.</p>
          <div className="deck-grid rest-grid">
            {listDeck(deck).map(({ card, index }) => (
              <button
                key={card.id}
                type="button"
                className={`hand-card deck-card type-${card.type}${pickClass(picked, index)}`}
                disabled={disabled}
                aria-label={`Remove ${card.name}`}
                onMouseEnter={() => sfx.play("hover")}
                onClick={() => {
                  sfx.play("reward_pick");
                  pickChoice(index);
                  onRemove(index);
                }}
              >
                <CardFace card={card} />
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
