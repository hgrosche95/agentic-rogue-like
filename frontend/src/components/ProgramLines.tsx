import type { CSSProperties, PointerEvent } from "react";
import {
  CONTROL_FLOW_TYPES,
  PERMANENT_CARD_TYPES,
  type Card,
  type HandCardView,
  type PendingCombatView,
  type ProgramStep,
} from "../api";
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
      {hot && (
        <b className="hot-mark" data-keyword="hot-path">
          HOT
        </b>
      )}
    </span>
  );
}

// The pipeline's end: what the program will hit the enemy for, in big - and,
// while it runs, what it has hit so far (`live`: the damage landed, the lines
// run).
function PipelineResult({ combat, live }: { combat: PendingCombatView; live: { dealt: number; lines: number } | null }) {
  const after = combat.program_preview;
  const queued = combat.program.some((card) => card !== null);
  const dealt = after ? combat.enemy_hp + combat.enemy_block - after.enemy_hp - after.enemy_block : 0;
  const block = after ? after.player_block - combat.player_block : 0;
  const lethal = queued && after !== null && after.enemy_hp <= 0;
  const left = after?.enemy_hp ?? combat.enemy_hp;
  return (
    <div
      className={`pipeline-result${lethal ? " is-lethal" : ""}${live ? " is-live" : ""}${queued ? "" : " is-idle"}`}
      aria-live="polite"
    >
      <span className="pipeline-target">→ {combat.enemy_name}</span>
      <b className="pipeline-total" key={live ? live.dealt : "plan"}>
        {live ? live.dealt : queued ? dealt : "–"}
      </b>
      <span className="pipeline-unit">damage{!live && block > 0 && ` · +${block} block`}</span>
      <span className="pipeline-after">
        {live
          ? `${live.lines} line${live.lines === 1 ? "" : "s"} run`
          : !queued
            ? "nothing queued"
            : lethal
              ? "clean exit"
              : `${left} HP left`}
      </span>
    </div>
  );
}

// Over a queued line: what it will do when the program runs (the preview's
// step for it) - a hit, a combo, block, or what its control flow steers.
function lineChip(card: Card, step: ProgramStep | undefined, next: ProgramStep | undefined, before: ProgramStep[]) {
  if (!step) return null;
  if (step.outcome === "cut") return { text: "cut", tone: "cut" };
  if (step.outcome === "skipped") return { text: "–", tone: "idle" };
  if (CONTROL_FLOW_TYPES.includes(card.type)) {
    if (card.type === "loop") {
      // a loop repeats the last action run before it - with none, it idles
      const repeats = before.some((s) => s.outcome === "ran" && !CONTROL_FLOW_TYPES.includes(s.type));
      return repeats ? { text: "↺ again", tone: "flow" } : { text: "nothing to repeat", tone: "idle" };
    }
    if (card.type === "if_wounded") {
      return next && next.runs > 1 ? { text: "×2 armed", tone: "flow" } : { text: "waiting", tone: "idle" };
    }
    if (card.type === "fork") return { text: "×2 next", tone: "flow" };
    return { text: "flow", tone: "flow" };
  }
  if (step.dealt > 0) return { text: step.runs > 1 ? `${step.runs}× = ${step.dealt}` : `${step.dealt}`, tone: "damage" };
  if (step.block > 0) return { text: `+${step.block}`, tone: "block" };
  if (step.heal > 0) return { text: `+${step.heal} HP`, tone: "heal" };
  return null;
}

// The link on the rail from a line to the next: a fork doubling it, a loop
// reaching back, or the interrupt's cut.
function linkKind(combat: PendingCombatView, line: number, cutLines: number[]): string {
  const card = combat.program[line];
  const next = combat.program[line + 1];
  if (cutLines.includes(line + 1) && !cutLines.includes(line)) return "cut";
  if (next?.type === "loop") return "loop";
  if (card && ["fork", "if_wounded"].includes(card.type)) return "fork";
  return "plain";
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
  live,
  reversed,
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
  // while the program runs: the damage landed and the lines run so far
  live: { dealt: number; lines: number } | null;
  // a refactor runs it right to left
  reversed: boolean;
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
        <span className="background-label">bg bus</span>
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
            {cardSelected && (
              <kbd className="key-hint" aria-hidden="true">
                B
              </kbd>
            )}
          </span>
        ) : (
          running.length === 0 && <span className="background-hint">Permanents run here</span>
        )}
      </button>
    );
  }

  const steps = combat.program_preview?.steps ?? [];
  return (
    <div
      className={`program-board${reversed ? " is-reversed" : ""}`}
      style={{ "--lines": combat.program.length } as CSSProperties}
    >
      {/* the pipeline: from the player's side, through the lines, into the enemy */}
      <div className="pipeline">
        <span className="pipeline-source" aria-hidden="true">
          {reversed ? "◂" : "▸"}
        </span>
        <div className="field program-lines">
          {combat.program.map((card, line) => {
            const at = steps.findIndex((s) => s.slot === line);
            const chip = card && at >= 0 ? lineChip(card, steps[at], steps[at + 1], steps.slice(0, at)) : null;
            return (
              <div
                key={line}
                className={`program-line${line === hotLine ? " is-hot" : ""}${running === line ? " is-running" : ""}${spentLines.includes(line) ? " is-spent" : ""}`}
              >
                <span className={`line-chip${chip ? ` is-${chip.tone}` : " is-none"}`}>{chip?.text}</span>
                {renderAction(card, line)}
                {line < combat.program.length - 1 && (
                  <span className={`line-link is-${linkKind(combat, line, cutLines)}`} aria-hidden="true" />
                )}
              </div>
            );
          })}
        </div>
        <PipelineResult combat={combat} live={live} />
      </div>
      {renderBackground()}
    </div>
  );
}
