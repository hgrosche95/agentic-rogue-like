import { useState } from "react";
import { PERMANENT_CARD_TYPES, type Card, type HandCardView, type PendingCombatView } from "../api";

function CardFace({ card }: { card: Card }) {
  const isPermanent = PERMANENT_CARD_TYPES.includes(card.type);
  return (
    <>
      {isPermanent && <span className="permanent-badge" title="Permanent - stays on the field">∞</span>}
      <span className="hand-card-name">{card.name}</span>
      <span className="hand-card-description">{card.description}</span>
    </>
  );
}

export function CombatPanel({
  combat,
  disabled,
  onPlayCard,
  onEndTurn,
}: {
  combat: PendingCombatView;
  disabled: boolean;
  onPlayCard: (handIndex: number, slotIndex: number) => void;
  onEndTurn: () => void;
}) {
  const [selectedHandIndex, setSelectedHandIndex] = useState<number | null>(null);
  const enemyHpPercent = Math.max(0, Math.min(100, (combat.enemy_hp / combat.enemy_max_hp) * 100));

  function selectCard(handIndex: number) {
    setSelectedHandIndex((current) => (current === handIndex ? null : handIndex));
  }

  function playIntoSlot(slotIndex: number) {
    if (selectedHandIndex === null) return;
    onPlayCard(selectedHandIndex, slotIndex);
    setSelectedHandIndex(null);
  }

  return (
    <div className="combat-panel">
      <div className="enemy-status">
        <span className="enemy-name">{combat.enemy_name}</span>
        <span className="hp-track enemy-hp-track">
          <span className="hp-fill enemy-hp-fill" style={{ width: `${enemyHpPercent}%` }} />
        </span>
        <span className="stat-figure">
          {combat.enemy_hp}/{combat.enemy_max_hp}
        </span>
      </div>

      <div className="combat-resources">
        {combat.player_block > 0 && <span className="block-badge">Block {combat.player_block}</span>}
        {combat.armor > 0 && <span className="armor-badge">Armor {combat.armor}</span>}
        <span className="pile-counts">
          Deck {combat.draw_count} · Discard {combat.discard_count}
        </span>
      </div>

      <p className="field-hint">
        {selectedHandIndex === null
          ? "Select a card from your hand, then play it onto an empty field slot."
          : "Choose an empty slot to play the selected card."}
      </p>

      <div className="field">
        {combat.field.map((card, slotIndex) =>
          card === null ? (
            <button
              key={slotIndex}
              className={`field-slot is-empty${selectedHandIndex !== null ? " is-targetable" : ""}`}
              disabled={disabled || selectedHandIndex === null}
              onClick={() => playIntoSlot(slotIndex)}
            >
              {slotIndex + 1}
            </button>
          ) : (
            <div key={slotIndex} className={`field-slot is-occupied type-${card.type}`}>
              <CardFace card={card} />
            </div>
          ),
        )}
      </div>

      <div className="hand">
        {combat.hand.map((card: HandCardView) => (
          <button
            key={card.hand_index}
            className={`hand-card type-${card.type}${selectedHandIndex === card.hand_index ? " is-selected" : ""}`}
            disabled={disabled}
            onClick={() => selectCard(card.hand_index)}
          >
            <CardFace card={card} />
          </button>
        ))}
      </div>

      <button className="end-turn-button" disabled={disabled} onClick={onEndTurn}>
        End turn
      </button>
    </div>
  );
}
