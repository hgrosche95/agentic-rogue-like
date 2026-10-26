import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  ATTACKING_INTENTS,
  PERMANENT_CARD_TYPES,
  type HandCardView,
  type PendingCombatView,
  type PlayerState,
  type Status,
} from "../api";
import { cardSound, hitsOf, sfx } from "../audio";
import { flyCard } from "../cardFlight";
import { ArtifactBar } from "./ArtifactBar";
import { HERO } from "../characters";
import { TYPING_MS, commandFor, type HackerCommand } from "../hackerCommands";
import { useCardDrag } from "../hooks/useCardDrag";
import { useHpExchange } from "../hooks/useHpExchange";
import { ENEMY_HIT_MS, PLAYER_HIT_MS, useLagged } from "../hooks/useLagged";
import { describeIntent, rangeText, STATUS_TEXT } from "../readouts";
import { CardFace, type Readout } from "./CardFace";
import { CombatHelp, HelpButton } from "./CombatHelp";
import { CombatArena, IntentIcon, type ArenaHandle } from "./CombatArena";
import { programPlan, queues } from "../program";
import { ProgramLines, ProgramOutput } from "./ProgramLines";
import { SlotPreview } from "./SlotPreview";

// The Vibe-Coder's context window: one pip per token, lit while used; past
// the window the extra pips glow red - every card from there may hallucinate.
function TokenMeter({ combat }: { combat: PendingCombatView }) {
  const limit = combat.token_limit ?? 0;
  const pips = Math.max(limit, combat.tokens_used);
  const full = combat.tokens_used >= limit;
  return (
    <span
      className={`token-meter${full ? " is-full" : ""}`}
      title={`Context window: ${combat.tokens_used}/${limit} tokens used, ${combat.token_regen} free up at the end of the turn. Cards past the window may hallucinate.`}
    >
      <span className="token-label">Context</span>
      <span className="token-pips" aria-hidden="true">
        {Array.from({ length: pips }, (_, i) => (
          <i key={i} className={i >= limit ? "is-over" : i < combat.tokens_used ? "is-used" : undefined} />
        ))}
      </span>
      <span className="token-count">
        {combat.tokens_used}/{limit}
      </span>
    </span>
  );
}

// Malware, Exposed, Throttled on one side, with what's left of each.
function StatusBadges({ statuses }: { statuses: Partial<Record<Status, number>> }) {
  return (
    <>
      {(Object.entries(statuses) as [Status, number][]).map(([status, left]) => (
        <span key={status} className={`status-badge is-${status}`} title={STATUS_TEXT[status]}>
          {status} {left}
        </span>
      ))}
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
      <em>
        {hp} / {max}
      </em>
    </span>
  );
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
// further from the middle and dropped along an arc. Past five cards the arc
// flattens, so the outer cards of a big hand (over the limit, about to
// discard) don't sink off the bottom of the screen.
function fanStyle(index: number, count: number): CSSProperties {
  const edge = Math.max(1, (count - 1) / 2);
  const k = index - (count - 1) / 2;
  const rot = k * Math.min(2.5, 6 / edge);
  const lift = k * k * Math.min(2.5, 12 / (edge * edge));
  return { "--rot": `${rot}deg`, "--lift": `${lift}px` } as CSSProperties;
}

// how long each program line stays lit while the program runs - long enough
// for its card animation to play out before the next line starts
const PROGRAM_STEP_MS = 1100;

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
  onMoveQueued,
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
  onMoveQueued?: (fromSlot: number, toSlot: number) => void;
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
  // Program mode: the line lit up while the program runs, before the end of
  // the turn goes to the server - and the queued card picked up to move,
  // which, like the discard picks, belongs to the table it was picked on.
  const [running, setRunning] = useState<number | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [moveChoice, setMoveChoice] = useState<{ on: PendingCombatView; line: number } | null>(null);
  const movingLine = moveChoice?.on === combat ? moveChoice.line : null;
  const setMovingLine = (line: number | null) => setMoveChoice(line === null ? null : { on: combat, line });
  const busy = disabled || typing || running !== null;
  const programMode = combat.program_mode;
  // the order the program runs in - reversed by a refactor, cut by an interrupt
  const { queuedLines, cutAfter, reversed, runningLines, cutLines } = programPlan(combat, enemySlain);
  const hotLine = (player.artifacts.find((a) => a.hot_path > 0)?.hot_path ?? 0) - 1;
  // The card just played, shown as already gone from the hand (and, for a
  // permanent card, as lying in its slot) until the server answers, so the
  // table doesn't sit still through the typing and the round trip and then
  // jump. Once nothing is in flight any more it is dropped - the server's
  // state has replaced it, or the move failed and the card stays in hand.
  const [played, setPlayed] = useState<{ handIndex: number; slotIndex: number } | null>(null);
  const pending = busy ? played : null;
  const pendingCard = pending && combat.hand.find((c) => c.hand_index === pending.handIndex);
  const handRef = useRef<HTMLDivElement>(null);
  const arenaRef = useRef<ArenaHandle>(null);
  // What the table looked like when the turn was ended, to tell once the
  // server answers whether the daemon fired and the enemy's blow got through.
  const endTurnFrom = useRef<{ combat: PendingCombatView; hp: number } | null>(null);

  useEffect(() => {
    const before = endTurnFrom.current;
    if (!before || before.combat === combat) return;
    endTurnFrom.current = null;
    const daemon = before.combat.field.some((card) => card?.type === "turret");
    const attacked = ATTACKING_INTENTS.includes(before.combat.enemy_intent) && !enemySlain;
    arenaRef.current?.enemyTurn({
      attacked,
      blocked: player.hp >= before.hp,
      braced: ["defend", "charge"].includes(before.combat.enemy_intent) && !enemySlain,
      daemon,
    });
    if (daemon) sfx.play("daemon_tick");
    if (!attacked) return;
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
    const picks = discarding ?? [];
    const finish = () => {
      endTurnFrom.current = { combat, hp: player.hp };
      onEndTurn(picks);
      setDiscarding(null);
    };
    setMovingLine(null);
    if (runningLines.length === 0) {
      finish();
      return;
    }
    // Run the program: each queued line lights up in turn, then the server
    // works the turn out and the HP bars move as usual.
    runningLines.forEach((line, step) => {
      window.setTimeout(() => {
        const card = combat.program[line];
        setRunning(line);
        if (!card) return;
        sfx.play(cardSound(card.type), { hits: hitsOf(card.description) });
        arenaRef.current?.cardPlayed(card.type, card.value);
      }, step * PROGRAM_STEP_MS);
    });
    window.setTimeout(() => {
      setRunning(null);
      finish();
    }, runningLines.length * PROGRAM_STEP_MS);
  }

  // Program mode: pick a queued card up, then put it on another line - an
  // occupied line swaps the two. Picking the same line again puts it back.
  function pickLine(line: number) {
    sfx.play("select");
    setSelectedHandIndex(null);
    if (movingLine === null) {
      if (combat.program[line]) setMovingLine(line);
      return;
    }
    setMovingLine(null);
    if (movingLine !== line) onMoveQueued?.(movingLine, line);
  }

  function selectCard(handIndex: number) {
    sfx.play("select");
    setMovingLine(null);
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
    // A card that queues into the program only runs at the end of the turn,
    // so its animation waits for "Run program" (see endTurn).
    const runsNow = !queues(combat, played);
    window.setTimeout(() => {
      setTyping(false);
      // Enter, and the command runs
      sfx.play("enter");
      if (runsNow) {
        sfx.play(cardSound(played.type), { hits: hitsOf(played.description), delayMs: 40 });
        arenaRef.current?.cardPlayed(played.type, played.value);
      }
      onPlayCard(handIndex, slotIndex);
    }, TYPING_MS + 150);
  }

  const drag = useCardDrag({
    enabled: !busy && discarding === null,
    onDrop: (handIndex, slotIndex, slot, from) => playIntoSlot(slotIndex, slot, handIndex, from),
  });
  // Program mode: drag a queued card onto another line to move it there.
  const lineDrag = useCardDrag({
    enabled: !busy && discarding === null,
    onDrop: (fromLine, toLine) => {
      setMovingLine(null);
      if (fromLine !== toLine) {
        sfx.play("select");
        onMoveQueued?.(fromLine, toLine);
      }
    },
  });

  // the card being aimed (selected or dragged) and the slot it is aimed at
  const aimedIndex = discarding === null ? (drag.dragging ?? selectedHandIndex) : null;
  const aimedCard = aimedIndex === null ? undefined : combat.hand.find((c) => c.hand_index === aimedIndex);
  const aimedSlot = drag.dragging !== null ? drag.hoverSlot : pointedSlot;
  const aimedLow = aimedCard && readoutOf(aimedCard, null);
  const attacking = ATTACKING_INTENTS.includes(combat.enemy_intent);
  const intent = describeIntent(
    combat.enemy_intent,
    combat.enemy_intent_min,
    combat.enemy_intent_max,
    combat.enemy_intent_hits,
    combat.enemy_intent_name,
  );

  return (
    <div className="combat-panel">
      {helpOpen && <CombatHelp programMode={programMode} onClose={() => setHelpOpen(false)} />}
      {/* the HUD plates sit in the scene's top corners, clear of the monitor */}
      <div className="arena-wrap">
        <CombatArena
          ref={arenaRef}
          status={{
            block: combat.player_block,
            armor: combat.armor,
            enemyBlock: combat.enemy_block,
            turrets: combat.field.filter((card) => card?.type === "turret").length,
            amplifiers: combat.field.filter((card) => card?.type === "amplifier").length,
            fortify: combat.field.filter((card) => card?.type === "fortify").length,
          }}
          enemy={{
            name: combat.enemy_name,
            maxHp: combat.enemy_max_hp,
            attack: combat.enemy_attack,
            setting,
            intent: combat.enemy_intent,
            intentMin: combat.enemy_intent_min,
            intentMax: combat.enemy_intent_max,
            intentHits: combat.enemy_intent_hits,
            intentName: combat.enemy_intent_name,
          }}
          exchange={exchange}
          log={log}
          commands={commands}
          typing={typing}
          slain={enemySlain}
          onContinue={onContinue}
          hero={player.character}
          contextFull={combat.token_limit !== null && combat.tokens_used >= combat.token_limit}
        />

        <div className="vs-hud is-player">
          <div className="vs-body">
            <span className="hud-name">
              {HERO[player.character].name} <small>Human · {era}</small>
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
              <StatusBadges statuses={combat.player_status} />
              {combat.token_limit !== null && <TokenMeter combat={combat} />}
              <ArtifactBar artifacts={player.artifacts} compact />
            </div>
          </div>
        </div>

        <div className="vs-hud is-enemy">
          <div className="vs-body">
            <span className="hud-name">
              {combat.enemy_name} <small>{combat.boss ? "Core AI" : "AI construct"} · {era}</small>
            </span>
            {combat.enemy_description && (
              <p className="hud-flavor" title={combat.enemy_description}>
                {combat.enemy_description}
              </p>
            )}
            <HpBar hp={shownEnemyHp} max={combat.enemy_max_hp} side="enemy" />
            <div className="hud-meta">
              {!enemySlain && (
                <span
                  className={`intent-badge type-${combat.enemy_intent} ${attacking ? "is-hit" : "is-guard"}`}
                  title={intent.title}
                >
                  <IntentIcon intent={combat.enemy_intent} />
                  {intent.label} {intent.amount}
                </span>
              )}
              {combat.enemy_affix && !enemySlain && (
                <span
                  className={`phase-badge affix-badge${combat.enemy_enraged ? " is-enraged" : ""}`}
                  title={combat.enemy_affix_description ?? undefined}
                >
                  {combat.enemy_affix}
                  {combat.enemy_enraged && " · raging"}
                </span>
              )}
              {combat.boss && !enemySlain && (
                <span
                  className={`phase-badge${combat.enemy_phase > 1 ? " is-enraged" : ""}`}
                  title={[
                    combat.enemy_phase > 1
                      ? `Overclocked: +${combat.enemy_strength} attack, and it purges permanents.`
                      : "Overclocks into phase 2 at half HP.",
                    combat.enemy_phases > 2 && combat.enemy_phase < 3
                      ? "Phase 3 at a quarter HP: stronger again, no more bracing, 4-hit barrages."
                      : "",
                  ].join(" ")}
                >
                  Phase {combat.enemy_phase}/{combat.enemy_phases}
                  {combat.enemy_strength > 0 && ` · +${combat.enemy_strength} ATK`}
                </span>
              )}
              {combat.enemy_block > 0 && (
                <span className="block-badge enemy-block-badge">Block {combat.enemy_block}</span>
              )}
              {!enemySlain && <StatusBadges statuses={combat.enemy_status} />}
              {enemySlain && <span className="intent-badge is-defeated">Defeated</span>}
            </div>
          </div>
        </div>
      </div>

      {/* the stack stands on the arena floor */}
      <div className="combat-row">
        <div className="field-zone">
          <div className="zone-head">
            <span className="zone-label zone-title">
              {programMode ? `Program · runs ${reversed ? "right to left" : "left to right"}` : "Execution stack"}
              <HelpButton
                onClick={() => {
                  sfx.play("click");
                  setHelpOpen(true);
                }}
              />
            </span>
            {programMode && <ProgramOutput combat={combat} playerHp={player.hp} />}
            {programMode && cutAfter !== null && !enemySlain && (
              <span
                className="interrupt-note"
                title="The enemy cuts your program off: queued lines after these don't run this turn"
              >
                Interrupt after {cutAfter} line{cutAfter === 1 ? "" : "s"}
              </span>
            )}
            <span className="zone-label">
              Hand {combat.hand.length}/{combat.max_hand_size}
            </span>
          </div>
          {programMode ? (
            <ProgramLines
              combat={combat}
              hotLine={hotLine}
              running={running}
              cutLines={cutLines}
              movingLine={movingLine}
              locked={busy || discarding !== null}
              pending={pending && pendingCard ? { slotIndex: pending.slotIndex, card: pendingCard } : null}
              aimedCard={aimedCard}
              aimedLow={aimedLow?.value}
              cardSelected={selectedHandIndex !== null}
              handHoverSlot={drag.hoverSlot}
              lineDrag={lineDrag}
              onPickLine={pickLine}
              onPlay={(line, slot) => playIntoSlot(line, slot)}
              onPoint={(line, over) => setPointedSlot((s) => (over ? line : s === line ? null : s))}
            />
          ) : (
          <div className="field">
            {combat.field.map((card, slotIndex) => {
              return card === null && pendingCard && pending?.slotIndex === slotIndex &&
                PERMANENT_CARD_TYPES.includes(pendingCard.type) ? (
                <div key={slotIndex} className={`field-slot is-occupied is-landing type-${pendingCard.type}`}>
                  <CardFace card={pendingCard} onField />
                </div>
              ) : card === null && combat.locked_slots.includes(slotIndex) ? (
                <div key={slotIndex} className="field-slot is-locked" title="Locked by the enemy for this turn">
                  <span className="slot-lock">Locked</span>
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
              );
            })}
          </div>
          )}
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
                className={`hand-card type-${card.type}${selectedHandIndex === card.hand_index ? " is-selected" : ""}${pending?.handIndex === card.hand_index ? " is-played" : ""}${discarding?.includes(card.hand_index) ? " is-discarding" : ""}${drag.dragging === card.hand_index ? " is-dragged" : ""}${card.overflows ? " is-overflowing" : ""}`}
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
            {discarding !== null
              ? "Discard & end turn"
              : queuedLines.length > 0
                ? "Run program"
                : "End turn"}
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
          : running !== null
            ? `Running line ${running + 1}...`
          : discarding !== null
            ? `Hand limit is ${combat.max_hand_size}: pick ${excess} card(s) to discard (${discarding.length}/${excess}).`
            : selectedHandIndex !== null &&
                combat.hand.find((card) => card.hand_index === selectedHandIndex)?.overflows
            ? "Context window full - this card may hallucinate and backfire. Choose a slot to risk it."
            : movingLine !== null
            ? `Moving line ${movingLine + 1}: click another line - an occupied one swaps.`
            : programMode && selectedHandIndex === null
            ? "Attacks, blocks and heals queue into the lines; permanents go into the socket under a line and boost the lines to its right. Drag a queued card to move it."
            : programMode && aimedCard && queues(combat, aimedCard)
            ? "Choose a program line - it runs at the end of the turn, left to right."
            : programMode && aimedCard && PERMANENT_CARD_TYPES.includes(aimedCard.type)
            ? "Choose a socket under a line - it boosts the lines to its right."
            : programMode && aimedCard
            ? "Choose a socket - this card runs right away, not in the program."
            : selectedHandIndex === null
            ? "Drag a card onto an empty slot of the stack - or click it, then click a slot."
            : "Choose an empty slot to run the selected card."}
      </p>
    </div>
  );
}
