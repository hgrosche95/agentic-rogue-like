import { useRef, useState } from "react";
import {
  PERMANENT_CARD_TYPES,
  type Card,
  type HandCardView,
  type PendingCombatView,
  type PlayerState,
} from "../api";
import { flyCard } from "../cardFlight";
import { useHpExchange } from "../hooks/useHpExchange";
import { CombatArena } from "./CombatArena";

function CardFace({ card }: { card: Card }) {
  const isPermanent = PERMANENT_CARD_TYPES.includes(card.type);
  return (
    <>
      <div className="card-header">{card.name}</div>
      <span className="card-rank">{isPermanent ? "∞" : card.value}</span>
      <div className="card-body">{card.description}</div>
    </>
  );
}

function Pile({ label, count, kind }: { label: string; count: number; kind: string }) {
  return (
    <div className={`pile pile-${kind}`}>
      <div className="pile-face">
        <span className="pile-count">{count}</span>
      </div>
      <span className="pile-label">{label}</span>
    </div>
  );
}

function HpBar({ hp, max, side }: { hp: number; max: number; side: "player" | "enemy" }) {
  const percent = Math.max(0, Math.min(100, (hp / max) * 100));
  return (
    <span className={`hud-bar is-${side}`}>
      <span style={{ width: `${percent}%` }} />
    </span>
  );
}

export function CombatPanel({
  combat,
  player,
  log,
  disabled,
  onPlayCard,
  onEndTurn,
}: {
  combat: PendingCombatView;
  player: PlayerState;
  log: string[];
  disabled: boolean;
  onPlayCard: (handIndex: number, slotIndex: number) => void;
  onEndTurn: () => void;
}) {
  const [selectedHandIndex, setSelectedHandIndex] = useState<number | null>(null);
  const exchange = useHpExchange(player.hp, combat.enemy_hp);
  const handRef = useRef<HTMLDivElement>(null);

  function selectCard(handIndex: number) {
    setSelectedHandIndex((current) => (current === handIndex ? null : handIndex));
  }

  function playIntoSlot(slotIndex: number, slot: HTMLElement) {
    if (selectedHandIndex === null) return;
    const card = handRef.current?.querySelector<HTMLElement>(`[data-hand-index="${selectedHandIndex}"]`);
    if (card) flyCard(card, slot);
    onPlayCard(selectedHandIndex, slotIndex);
    setSelectedHandIndex(null);
  }

  return (
    <div className="combat-panel">
      <CombatArena exchange={exchange} log={log}>
        <div className="combat-hud">
          <div className="hud-side is-player">
            <span className="hud-name">Dr. Chronos</span>
            <HpBar hp={player.hp} max={player.max_hp} side="player" />
            <div className="hud-meta">
              <span className="stat-figure">
                {player.hp}/{player.max_hp}
              </span>
              {combat.player_block > 0 && <span className="block-badge">Block {combat.player_block}</span>}
              {combat.armor > 0 && <span className="armor-badge">Armor {combat.armor}</span>}
            </div>
          </div>

          <div className="hud-side is-enemy">
            <span className="hud-name">{combat.enemy_name}</span>
            <HpBar hp={combat.enemy_hp} max={combat.enemy_max_hp} side="enemy" />
            <div className="hud-meta">
              {combat.enemy_block > 0 && (
                <span className="block-badge enemy-block-badge">Block {combat.enemy_block}</span>
              )}
              <span className={`intent-badge type-${combat.enemy_intent}`}>
                {combat.enemy_intent === "attack" ? "Attacking" : "Defending"} · {combat.enemy_intent_value}
              </span>
              <span className="stat-figure">
                {combat.enemy_hp}/{combat.enemy_max_hp}
              </span>
            </div>
          </div>
        </div>
      </CombatArena>

      <div className="field-zone">
        <span className="zone-label">Field</span>
        <div className="field">
          {combat.field.map((card, slotIndex) =>
            card === null ? (
              <button
                key={slotIndex}
                className={`field-slot is-empty${selectedHandIndex !== null ? " is-targetable" : ""}`}
                disabled={disabled || selectedHandIndex === null}
                onClick={(event) => playIntoSlot(slotIndex, event.currentTarget)}
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
      </div>

      <div className="battlefield">
        <Pile label="Deck" count={combat.draw_count} kind="deck" />

        <div className="hand-zone">
          <span className="zone-label">Hand</span>
          <div className="hand" ref={handRef}>
            {combat.hand.map((card: HandCardView) => (
              <button
                key={card.hand_index}
                data-hand-index={card.hand_index}
                className={`hand-card type-${card.type}${selectedHandIndex === card.hand_index ? " is-selected" : ""}`}
                disabled={disabled}
                onClick={() => selectCard(card.hand_index)}
              >
                <CardFace card={card} />
              </button>
            ))}
          </div>
        </div>

        <div className="table-side">
          <button className="end-turn-button" disabled={disabled} onClick={onEndTurn}>
            End turn
          </button>
          <div className="side-piles">
            <Pile label="Graveyard" count={combat.discard_count} kind="graveyard" />
            <Pile label="Banished" count={combat.banished_count} kind="banished" />
          </div>
        </div>
      </div>

      <p className="field-hint">
        {selectedHandIndex === null
          ? "Select a card from your hand, then play it onto an empty field slot."
          : "Choose an empty slot to play the selected card."}
      </p>
    </div>
  );
}
