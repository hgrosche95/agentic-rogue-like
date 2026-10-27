import type { PointerEvent } from "react";
import { PERMANENT_CARD_TYPES, type Card, type HandCardView, type PendingCombatView } from "../api";
import { cardText, queues } from "../program";
import { CardFace, CardTypeIcon } from "./CardFace";
import { SlotPreview } from "./SlotPreview";

// Program mode's part of the stack: one row of lines, each a queued action,
// the background the permanents run in under it, and the line saying what the
// program will do. CombatPanel owns the state (what is aimed, picked up, dragged,
// running); this only draws it and reports clicks back.

// Program mode: where the fight will stand once the queued program has run -
// the enemy's HP and block and the player's block after it, next to now.
export function ProgramOutput({ combat, playerHp }: { combat: PendingCombatView; playerHp: number }) {
  const after = combat.program_preview;
  if (!after || combat.program.every((card) => card === null)) {
    return <span className="program-output is-idle">Nothing queued</span>;
  }
  const dealt = combat.enemy_hp + combat.enemy_block - after.enemy_hp - after.enemy_block;
  return (
    <span
      className="program-output"
      title="What the program will have done by the time the enemy acts - cards it draws left out"
    >
      <span className={after.enemy_hp <= 0 ? "is-lethal" : undefined}>
        Enemy {after.enemy_hp <= 0 ? "down" : `${after.enemy_hp} HP`}
        {after.enemy_block > 0 && after.enemy_hp > 0 && ` · ${after.enemy_block} block`}
        {dealt > 0 && <em> (−{dealt})</em>}
      </span>
      {(after.player_block > combat.player_block || after.player_hp !== playerHp) && (
        <span className={after.player_hp < playerHp ? "is-hurt" : undefined}>
          You
          {after.player_hp !== playerHp && ` ${after.player_hp} HP`}
          {after.player_block > combat.player_block && ` · ${after.player_block} block`}
        </span>
      )}
    </span>
  );
}

// A program line: its number, the Hot Path mark, and - while a card is aimed
// at it - what that card would do from here.
function LineLabel({ index, hot }: { index: number; hot: boolean }) {
  return (
    <span className="line-label">
      {String(index + 1).padStart(2, "0")}
      {hot && <b className="hot-mark">HOT</b>}
    </span>
  );
}


// What CombatPanel's drag of queued cards between lines looks like from here
// (hooks/useCardDrag, with the line as the "hand index").
interface LineDrag {
  dragging: number | null;
  hoverSlot: number | null;
  onPointerDown: (event: PointerEvent<HTMLElement>, line: number) => void;
  consumeClick: () => boolean;
}

export function ProgramLines({
  combat,
  hotLine,
  running,
  cutLines,
  spentLines,
  movingLine,
  locked,
  pending,
  aimedCard,
  aimedLow,
  cardSelected,
  handHoverSlot,
  lineDrag,
  onPickLine,
  onPlay,
  onPoint,
}: {
  combat: PendingCombatView;
  hotLine: number;
  // the line lit up while the program runs
  running: number | null;
  cutLines: number[];
  // the lines that have already run this turn
  spentLines: number[];
  // the queued card picked up to move, by its line
  movingLine: number | null;
  // nothing can be clicked: a move in flight, or discards being picked
  locked: boolean;
  // the card just played, shown in place until the server answers
  pending: { slotIndex: number; card: HandCardView } | null;
  aimedCard: HandCardView | undefined;
  aimedLow: number | undefined;
  // a hand card is selected (not just dragged)
  cardSelected: boolean;
  handHoverSlot: number | null;
  lineDrag: LineDrag;
  onPickLine: (line: number) => void;
  onPlay: (line: number, slot: HTMLElement) => void;
  // the pointer entering (over) or leaving a line
  onPoint: (line: number, over: boolean) => void;
}) {
  const draggingLine = lineDrag.dragging;

  // a line's action (top) - queued, landing, empty or locked
  function renderAction(card: Card | null, line: number) {
    const hot = line === hotLine;
    const tags = `${hot ? " is-hot" : ""}${running === line ? " is-running" : ""}${cutLines.includes(line) ? " is-cut" : ""}${spentLines.includes(line) ? " is-spent" : ""}`;
    if (card === null && pending?.slotIndex === line && queues(combat, pending.card)) {
      return (
        <div className={`field-slot is-occupied is-queued is-landing type-${pending.card.type}${tags}`}>
          <CardFace card={pending.card} onField />
        </div>
      );
    }
    if (card === null && combat.locked_slots.includes(line)) {
      return (
        <div className="field-slot is-locked" title="Locked by the enemy for this turn">
          <span className="slot-lock">Locked</span>
        </div>
      );
    }
    if (card !== null) {
      const glitched = combat.program_glitched[line];
      const dropHere = draggingLine !== null && draggingLine !== line;
      return (
        <button
          data-slot-index={dropHere ? line : undefined}
          className={`field-slot is-occupied is-queued type-${card.type}${tags}${movingLine === line ? " is-moving" : ""}${(movingLine !== null && movingLine !== line) || dropHere ? " is-swap-target" : ""}${dropHere && lineDrag.hoverSlot === line ? " is-drop-target" : ""}${draggingLine === line ? " is-dragged" : ""}${glitched ? " is-glitched" : ""}`}
          disabled={locked}
          title={
            glitched
              ? "Played past the context window - it will hallucinate when it runs"
              : movingLine === null
                ? "Drag it - or click it, then a line - to move it"
                : undefined
          }
          onPointerDown={(event) => lineDrag.onPointerDown(event, line)}
          onClick={() => {
            if (!lineDrag.consumeClick()) onPickLine(line);
          }}
        >
          <span className="line-tag">
            {cutLines.includes(line) ? "cut" : line + 1}
            {hot && " · HOT"}
          </span>
          <CardFace card={card} onField />
        </button>
      );
    }
    const aimedHere = aimedCard !== undefined && queues(combat, aimedCard);
    const dropHere = aimedHere || draggingLine !== null;
    const hovered = aimedHere ? handHoverSlot : lineDrag.hoverSlot;
    return (
      <button
        data-slot-index={dropHere ? line : undefined}
        className={`field-slot is-empty${dropHere || movingLine !== null ? " is-targetable" : ""}${dropHere && hovered === line ? " is-drop-target" : ""}${tags}`}
        disabled={locked || (movingLine === null && (!cardSelected || !aimedHere))}
        onClick={(event) => (movingLine !== null ? onPickLine(line) : onPlay(line, event.currentTarget))}
        onPointerEnter={() => onPoint(line, true)}
        onPointerLeave={() => onPoint(line, false)}
      >
        {aimedHere ? (
          <SlotPreview index={line} card={aimedCard} low={aimedLow} />
        ) : (
          <LineLabel index={line} hot={hot} />
        )}
      </button>
    );
  }

  // The background, under the lines: every permanent running, as many as get
  // played - each one works on the whole program, wherever it lands. Card flow,
  // which still resolves on the spot, is dropped here too.
  function renderBackground() {
    const landing = pending && !queues(combat, pending.card) && PERMANENT_CARD_TYPES.includes(pending.card.type)
      ? pending.card
      : null;
    const aims = aimedCard !== undefined && !queues(combat, aimedCard);
    const running = [...combat.field.filter((card) => card !== null), ...(landing ? [landing] : [])];
    return (
      <button
        type="button"
        data-slot-index={aims ? 0 : undefined}
        className={`program-background${aims ? " is-targetable" : ""}${aims && handHoverSlot === 0 ? " is-drop-target" : ""}`}
        disabled={locked || !cardSelected || !aims}
        onClick={(event) => onPlay(0, event.currentTarget)}
        onPointerEnter={() => aims && onPoint(0, true)}
        onPointerLeave={() => aims && onPoint(0, false)}
      >
        <span className="background-label">bg</span>
        {running.map((card, i) => (
          <span
            key={i}
            className={`line-socket is-installed type-${card.type}${card === landing ? " is-landing" : ""}`}
            title={`${card.name}: ${cardText(card, true)}`}
          >
            <CardTypeIcon type={card.type} />
            <span>{card.name}</span>
          </span>
        ))}
        {aims ? (
          <span className="background-hint">
            {PERMANENT_CARD_TYPES.includes(aimedCard.type) ? "+ install" : "run now"}
          </span>
        ) : (
          running.length === 0 && <span className="background-hint">Permanents run here</span>
        )}
      </button>
    );
  }

  return (
    <div className="program-board">
      <div className="field program-lines">
        {combat.program.map((card, line) => (
          <div key={line} className={`program-line${line === hotLine ? " is-hot" : ""}`}>
            {renderAction(card, line)}
          </div>
        ))}
      </div>
      {renderBackground()}
    </div>
  );
}
