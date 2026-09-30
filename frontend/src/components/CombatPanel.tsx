import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  PERMANENT_CARD_TYPES,
  type HandCardView,
  type PendingCombatView,
  type PlayerState,
} from "../api";
import { cardSound, hitsOf, sfx } from "../audio";
import { flyCard } from "../cardFlight";
import { ArtifactBar } from "./ArtifactBar";
import { TYPING_MS, commandFor, type HackerCommand } from "../hackerCommands";
import { useCardDrag } from "../hooks/useCardDrag";
import { useHpExchange } from "../hooks/useHpExchange";
import { ENEMY_HIT_MS, PLAYER_HIT_MS, useLagged } from "../hooks/useLagged";
import { rangeText, unitOf } from "../readouts";
import { CardFace, type Readout } from "./CardFace";
import { CombatArena, IntentIcon } from "./CombatArena";

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
      <em>
        {hp} / {max}
      </em>
    </span>
  );
}

// An empty slot shows its number - and, while a card is aimed at the stack,
// what that card would do from here, lit up where an amplifier boosts it.
function SlotPreview({ index, card, low }: { index: number; card?: HandCardView; low?: number }) {
  const label = String(index + 1).padStart(2, "0");
  const value = card?.preview[index];
  const unit = card && unitOf(card.type);
  if (value === null || value === undefined || !unit) return <>{label}</>;
  return (
    <span className={`slot-preview${low !== undefined && value > low ? " is-boosted" : ""}`}>
      <span className="slot-no">{label}</span>
      <b>{value}</b>
      <span className="slot-unit">{unit}</span>
    </span>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

// What a hand card will come out with: in `slot` when the player is pointing
// at one, otherwise in the weakest free slot - with the best free slot as a
// hint that position matters. Undefined for cards without such a number.
function readoutOf(card: HandCardView, slot: number | null): Readout | undefined {
  const values = card.preview.filter((v): v is number => v !== null);
  if (values.length === 0) return undefined;
  const low = Math.min(...values);
  const best = Math.max(...values);
  const at = slot === null ? null : card.preview[slot];
  const value = at ?? low;
  return { value, best, boosted: value > low };
}

// The hand fans out like cards held in a hand: each one turned a little
// further from the middle and dropped along an arc.
function fanStyle(index: number, count: number): CSSProperties {
  const k = index - (count - 1) / 2;
  return { "--rot": `${k * 2.5}deg`, "--lift": `${k * k * 2.5}px` } as CSSProperties;
}

export function CombatPanel({
  combat,
  setting,
  player,
  era,
  log,
  disabled,
  enemySlain = false,
  onPlayCard,
  onEndTurn,
  onContinue,
}: {
  combat: PendingCombatView;
  setting: string;
  player: PlayerState;
  era: string;
  log: string[];
  disabled: boolean;
  enemySlain?: boolean;
  onPlayCard: (handIndex: number, slotIndex: number) => void;
  onEndTurn: (discardIndices: number[]) => void;
  onContinue?: () => void;
}) {
  const [selectedHandIndex, setSelectedHandIndex] = useState<number | null>(null);
  // the free slot the pointer rests on while a card is selected
  const [pointedSlot, setPointedSlot] = useState<number | null>(null);
  // Over the hand limit, ending the turn first asks which cards to discard.
  // The picks belong to the table they were made on, so any new state from
  // the server (a card played, a turn ended) drops them; null while not choosing.
  const [discardChoice, setDiscardChoice] = useState<{ on: PendingCombatView; picks: number[] } | null>(
    null,
  );
  const discarding = discardChoice?.on === combat ? discardChoice.picks : null;
  const setDiscarding = (picks: number[] | null) =>
    setDiscardChoice(picks === null ? null : { on: combat, picks });
  const excess = Math.max(0, combat.hand.length - combat.max_hand_size);
  const exchange = useHpExchange(player.hp, combat.enemy_hp);
  // the bars move when the hit lands, not when the server answers
  const shownPlayerHp = useLagged(player.hp, PLAYER_HIT_MS);
  const shownEnemyHp = useLagged(combat.enemy_hp, ENEMY_HIT_MS);
  const [commands, setCommands] = useState<HackerCommand[]>([]);
  const [typing, setTyping] = useState(false);
  const busy = disabled || typing;
  // The card just played, shown as already gone from the hand (and, for a
  // permanent card, as lying in its slot) until the server answers, so the
  // table doesn't sit still through the typing and the round trip and then
  // jump. Once nothing is in flight any more it is dropped - the server's
  // state has replaced it, or the move failed and the card stays in hand.
  const [played, setPlayed] = useState<{ handIndex: number; slotIndex: number } | null>(null);
  const pending = busy ? played : null;
  const pendingCard = pending && combat.hand.find((c) => c.hand_index === pending.handIndex);
  const handRef = useRef<HTMLDivElement>(null);
  // What the table looked like when the turn was ended, to tell once the
  // server answers whether the daemon fired and the enemy's blow got through.
  const endTurnFrom = useRef<{ combat: PendingCombatView; hp: number } | null>(null);

  useEffect(() => {
    const before = endTurnFrom.current;
    if (!before || before.combat === combat) return;
    endTurnFrom.current = null;
    if (before.combat.field.some((card) => card?.type === "turret")) sfx.play("daemon_tick");
    if (before.combat.enemy_intent !== "attack" || enemySlain) return;
    sfx.play("enemy_attack", { delayMs: 150 });
    // a hit through the block is voiced by the HP exchange (useHpExchange)
    if (player.hp >= before.hp && before.combat.player_block > 0) sfx.play("block_absorb", { delayMs: 300 });
  }, [combat, player.hp, enemySlain]);

  function endTurn() {
    sfx.play("click");
    if (excess > 0 && discarding === null) {
      setSelectedHandIndex(null);
      setDiscarding([]);
      return;
    }
    if (discarding !== null && discarding.length !== excess) return;
    endTurnFrom.current = { combat, hp: player.hp };
    onEndTurn(discarding ?? []);
    setDiscarding(null);
  }

  function selectCard(handIndex: number) {
    sfx.play("select");
    if (discarding !== null) {
      if (discarding.includes(handIndex)) setDiscarding(discarding.filter((i) => i !== handIndex));
      else if (discarding.length < excess) setDiscarding([...discarding, handIndex]);
      return;
    }
    setSelectedHandIndex((current) => (current === handIndex ? null : handIndex));
  }

  // `from` is where the card's flight into the slot starts: the card in the
  // hand, or the dragged copy where it was dropped.
  function playIntoSlot(slotIndex: number, slot: HTMLElement, handIndex = selectedHandIndex, from?: HTMLElement) {
    if (handIndex === null) return;
    endTurnFrom.current = null;
    const card = from ?? handRef.current?.querySelector<HTMLElement>(`[data-hand-index="${handIndex}"]`);
    if (card) flyCard(card, slot);
    setSelectedHandIndex(null);
    setPlayed({ handIndex, slotIndex });
    const played = combat.hand.find((c) => c.hand_index === handIndex);
    if (!played) {
      onPlayCard(handIndex, slotIndex);
      return;
    }
    // Dr. Chronos types the card in as a command first; it only goes to the
    // server - and hits - once he is done typing.
    const text = commandFor(played, combat.enemy_name);
    setCommands((sent) => [...sent, { at: log.length, text }]);
    setTyping(true);
    sfx.play("typing", { durationMs: TYPING_MS });
    window.setTimeout(() => {
      setTyping(false);
      // Enter, and the command runs
      sfx.play("enter");
      sfx.play(cardSound(played.type), { hits: hitsOf(played.description), delayMs: 40 });
      onPlayCard(handIndex, slotIndex);
    }, TYPING_MS + 150);
  }

  const drag = useCardDrag({
    enabled: !busy && discarding === null,
    onDrop: (handIndex, slotIndex, slot, from) => playIntoSlot(slotIndex, slot, handIndex, from),
  });

  // the card being aimed (selected or dragged) and the slot it is aimed at
  const aimedIndex = discarding === null ? (drag.dragging ?? selectedHandIndex) : null;
  const aimedCard = aimedIndex === null ? undefined : combat.hand.find((c) => c.hand_index === aimedIndex);
  const aimedSlot = drag.dragging !== null ? drag.hoverSlot : pointedSlot;
  const aimedLow = aimedCard && readoutOf(aimedCard, null);
  const attacking = combat.enemy_intent === "attack";

  return (
    <div className="combat-panel">
      <CombatArena
        enemy={{
          name: combat.enemy_name,
          maxHp: combat.enemy_max_hp,
          // an enemy's intent value is always its attack stat (api.py)
          attack: combat.enemy_intent_value,
          setting,
          intent: combat.enemy_intent,
          intentMin: combat.enemy_intent_min,
          intentMax: combat.enemy_intent_max,
        }}
        exchange={exchange}
        log={log}
        commands={commands}
        typing={typing}
        slain={enemySlain}
        onContinue={onContinue}
      />

      {/* the rift keeps going below the scene, between the two sides of the table */}
      <div className="combat-seam" aria-hidden="true" />

      <div className="combat-row">
        <div className="vs-hud is-player">
          <span className="vs-portrait" aria-hidden="true">
            <span>DC</span>
          </span>
          <div className="vs-body">
            <span className="hud-name">
              Dr. Chronos <small>Human · {era}</small>
            </span>
            <HpBar hp={shownPlayerHp} max={player.max_hp} side="player" />
            <div className="hud-meta">
              {attacking && !enemySlain && (
                <span
                  className={`incoming-badge${combat.incoming_max === 0 ? " is-safe" : ""}`}
                  title="What the enemy's attack does to you if you end the turn now - after block and armor"
                >
                  {combat.incoming_max === 0
                    ? "Fully blocked"
                    : `Incoming ${rangeText(combat.incoming_min, combat.incoming_max)}`}
                </span>
              )}
              {combat.player_block > 0 && <span className="block-badge">Block {combat.player_block}</span>}
              {combat.armor > 0 && <span className="armor-badge">Armor {combat.armor}</span>}
              <ArtifactBar artifacts={player.artifacts} compact />
            </div>
          </div>
        </div>

        <div className="field-zone">
          <div className="zone-head">
            <span className="zone-label">Execution stack</span>
            <span className="zone-label">
              Hand {combat.hand.length}/{combat.max_hand_size}
            </span>
          </div>
          <div className="field">
            {combat.field.map((card, slotIndex) =>
              card === null && pendingCard && pending?.slotIndex === slotIndex &&
              PERMANENT_CARD_TYPES.includes(pendingCard.type) ? (
                <div key={slotIndex} className={`field-slot is-occupied is-landing type-${pendingCard.type}`}>
                  <CardFace card={pendingCard} onField />
                </div>
              ) : card === null ? (
                <button
                  key={slotIndex}
                  data-slot-index={slotIndex}
                  className={`field-slot is-empty${aimedCard ? " is-targetable" : ""}${drag.hoverSlot === slotIndex ? " is-drop-target" : ""}`}
                  disabled={busy || selectedHandIndex === null || discarding !== null}
                  onClick={(event) => playIntoSlot(slotIndex, event.currentTarget)}
                  onPointerEnter={() => setPointedSlot(slotIndex)}
                  onPointerLeave={() => setPointedSlot((s) => (s === slotIndex ? null : s))}
                >
                  <SlotPreview index={slotIndex} card={aimedCard} low={aimedLow?.value} />
                </button>
              ) : (
                <div key={slotIndex} className={`field-slot is-occupied type-${card.type}`}>
                  <CardFace card={card} onField />
                </div>
              ),
            )}
          </div>
        </div>

        <div className="vs-hud is-enemy">
          <div className="vs-body">
            <span className="hud-name">
              {combat.enemy_name} <small>AI construct · {era}</small>
            </span>
            <HpBar hp={shownEnemyHp} max={combat.enemy_max_hp} side="enemy" />
            <div className="hud-meta">
              {!enemySlain && (
                <span className={`intent-badge type-${combat.enemy_intent}`}>
                  <IntentIcon intent={combat.enemy_intent} />
                  {attacking ? "Attack" : "Brace"} {rangeText(combat.enemy_intent_min, combat.enemy_intent_max)}
                </span>
              )}
              {combat.enemy_block > 0 && (
                <span className="block-badge enemy-block-badge">Block {combat.enemy_block}</span>
              )}
              {enemySlain && <span className="intent-badge is-defeated">Defeated</span>}
            </div>
          </div>
          <span className="vs-portrait" aria-hidden="true">
            <span>{initials(combat.enemy_name)}</span>
          </span>
        </div>
      </div>

      <div className="battlefield">
        <Pile label="Source" count={combat.draw_count} kind="deck" />

        <div className="hand-zone">
          <div className="hand" ref={handRef}>
            {combat.hand.map((card: HandCardView, i) => (
              <button
                key={card.hand_index}
                data-hand-index={card.hand_index}
                style={fanStyle(i, combat.hand.length)}
                className={`hand-card type-${card.type}${selectedHandIndex === card.hand_index ? " is-selected" : ""}${pending?.handIndex === card.hand_index ? " is-played" : ""}${discarding?.includes(card.hand_index) ? " is-discarding" : ""}${drag.dragging === card.hand_index ? " is-dragged" : ""}`}
                disabled={busy}
                onMouseEnter={() => sfx.play("hover")}
                onPointerDown={(event) => drag.onPointerDown(event, card.hand_index)}
                onClick={() => {
                  if (!drag.consumeClick()) selectCard(card.hand_index);
                }}
              >
                <CardFace card={card} readout={readoutOf(card, aimedIndex === card.hand_index ? aimedSlot : null)} />
              </button>
            ))}
          </div>
        </div>

        <div className="table-side">
          <button
            className="end-turn-button"
            disabled={busy || (discarding !== null && discarding.length !== excess)}
            onClick={endTurn}
          >
            {discarding === null ? "End turn" : "Discard & end turn"}
          </button>
          {discarding !== null && (
            <button className="end-turn-button is-cancel" disabled={busy} onClick={() => setDiscarding(null)}>
              Cancel
            </button>
          )}
          <div className="side-piles">
            <Pile label="Cache" count={combat.discard_count} kind="graveyard" />
            <Pile label="Purged" count={combat.banished_count} kind="banished" />
          </div>
        </div>
      </div>

      <p className="field-hint">
        {enemySlain
          ? "Enemy defeated."
          : discarding !== null
            ? `Hand limit is ${combat.max_hand_size}: pick ${excess} card(s) to discard (${discarding.length}/${excess}).`
            : selectedHandIndex === null
            ? "Drag a card onto an empty slot of the stack - or click it, then click a slot."
            : "Choose an empty slot to run the selected card."}
      </p>
    </div>
  );
}
