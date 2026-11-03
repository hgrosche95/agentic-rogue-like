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
  const combos = (after?.steps ?? []).flatMap((s) => (s.combo ? [s.combo] : []));
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
      {!live && combos.length > 0 && <span className="pipeline-combos">★ {combos.join(" · ")}</span>}
    </div>
  );
}

// Over a queued line: what it will do when the program runs (the preview's
// step for it) - a hit, a combo, block, or what its control flow steers.
function lineChip(card: Card, step: ProgramStep | undefined, next: ProgramStep | undefined, before: ProgramStep[]) {
  if (!step) return null;
  if (step.outcome === "cut") return { text: "cut", tone: "cut" };
  if (step.outcome === "collected") return { text: "collected", tone: "cut" };
  if (step.outcome === "skipped") return { text: "–", tone: "idle" };
  if (card.type === "retrieve") {
    // Undo, Rollback: what the lines before it leave in the graveyard comes back
    return step.retrieved.length > 0
      ? { text: `↩ ${step.retrieved.join(", ")}`, tone: "fetch" }
      : { text: "nothing to fetch", tone: "idle" };
  }
  if (CONTROL_FLOW_TYPES.includes(card.type)) {
    if (card.type === "goto") {
      const replayed = before.filter((s) => s.outcome === "ran" && !CONTROL_FLOW_TYPES.includes(s.type)).slice(0, card.value);
      return replayed.length > 0
        ? { text: `↑ 1 · ${replayed.length} again`, tone: "flow" }
        : { text: "nothing to jump to", tone: "idle" };
    }
    if (card.type === "loop") {
      // a loop repeats the last action run before it - with none, it idles
      const target = loopTarget(before);
      return target ? { text: `↺ ${target.name}`, tone: "flow" } : { text: "nothing to repeat", tone: "idle" };
    }
    if (card.type === "if_wounded" || card.type === "guard") {
      return next && next.runs > 1 ? { text: "×2 armed", tone: "flow" } : { text: "waiting", tone: "idle" };
    }
    if (card.type === "fork") return { text: "×2 next", tone: "flow" };
    if (card.type === "try_catch") return { text: "catch", tone: "flow" };
    if (card.type === "buffer") return { text: "→ buffer", tone: "flow" };
    if (card.type === "flush") return step.dealt > 0 ? { text: `${step.dealt} out`, tone: "damage" } : { text: "empty", tone: "idle" };
    return { text: "flow", tone: "flow" };
  }
  // a buffered action: its damage waits for a Flush
  if (step.dealt === 0 && before.at(-1)?.type === "buffer" && card.type !== "block" && card.type !== "heal") {
    return { text: "stored", tone: "flow" };
  }
  if (step.dealt > 0) return { text: step.runs > 1 ? `${step.runs}× = ${step.dealt}` : `${step.dealt}`, tone: "damage" };
  if (step.block > 0) return { text: `+${step.block}`, tone: "block" };
  if (step.heal > 0) return { text: `+${step.heal} HP`, tone: "heal" };
  return null;
}

// The action a loop repeats: the last one that ran before it.
function loopTarget(before: ProgramStep[]): ProgramStep | undefined {
  return before.findLast((s) => s.outcome === "ran" && !CONTROL_FLOW_TYPES.includes(s.type));
}

// The lines control flow works on, for a badge on their card: run more than
// once (a Fork, If Wounded, Tail Call in front of it) and repeated by a
// Loop or a Goto.
function boostsOf(
  steps: ProgramStep[],
  program: (Card | null)[],
): Map<number, { times: number; looped: boolean }> {
  const boosts = new Map<number, { times: number; looped: boolean }>();
  steps.forEach((step, i) => {
    if (step.outcome !== "ran") return;
    if (step.type === "goto") {
      const replayed = steps
        .slice(0, i)
        .filter((s) => s.outcome === "ran" && !CONTROL_FLOW_TYPES.includes(s.type))
        .slice(0, program[step.slot]?.value ?? 0);
      for (const target of replayed) {
        const b = boosts.get(target.slot) ?? { times: target.runs, looped: false };
        boosts.set(target.slot, { ...b, looped: true });
      }
    } else if (step.type === "loop") {
      const target = loopTarget(steps.slice(0, i));
      if (target) {
        const b = boosts.get(target.slot) ?? { times: target.runs, looped: false };
        boosts.set(target.slot, { ...b, looped: true });
      }
    } else if (!CONTROL_FLOW_TYPES.includes(step.type) && step.runs > 1) {
      boosts.set(step.slot, { times: step.runs, looped: boosts.get(step.slot)?.looped ?? false });
    }
  });
  return boosts;
}

// The lines the enemy's program move hits: the two a race condition swaps
// (they run in the order of the preview's steps) and the first line to
// run, which a memory leak locks for the next turn. A garbage collector's
// line already says "collected" in its chip.
function threatsOf(combat: PendingCombatView, steps: ProgramStep[]): Map<number, { text: string; title: string }> {
  const threats = new Map<number, { text: string; title: string }>();
  const ran = steps.filter((s) => s.outcome === "ran");
  if (combat.enemy_intent === "race") {
    for (const step of steps.slice(0, 2)) {
      if (steps.length >= 2) threats.set(step.slot, { text: "⇄", title: "Race Condition: swapped with the other marked line" });
    }
  }
  if (combat.enemy_intent === "leak" && ran[0]) {
    threats.set(ran[0].slot, { text: "leak", title: "Memory Leak: this line is locked for your next turn" });
  }
  return threats;
}

// The link on the rail from a line to the next: a fork doubling it, a loop
// reaching back, or the interrupt's cut.
function linkKind(combat: PendingCombatView, line: number, cutLines: number[]): string {
  const card = combat.program[line];
  const next = combat.program[line + 1];
  if (cutLines.includes(line + 1) && !cutLines.includes(line)) return "cut";
  // Segfault: the program ends after it
  if (card?.halts && combat.program.slice(line + 1).some((c) => c !== null)) return "cut";
  if (next?.type === "loop") return "loop";
  if (card && ["fork", "if_wounded", "guard"].includes(card.type)) return "fork";
  return "plain";
}

// The small "back to hand" button on a card lying on the field - a queued
// line or an installed permanent. Shared with CombatPanel's classic slots.
// A permanent that has run since an earlier turn isn't taken back but
// uninstalled - banished for the rest of the fight (`uninstall`).
export function TakeBack({
  name,
  disabled,
  onClick,
  uninstall = false,
}: {
  name: string;
  disabled: boolean;
  onClick: () => void;
  uninstall?: boolean;
}) {
  const label = uninstall
    ? `Uninstall ${name} - it is banished for the rest of the fight`
    : `Take ${name} back into your hand`;
  return (
    <button
      type="button"
      className={`take-back${uninstall ? " is-uninstall" : ""}`}
      disabled={disabled}
      title={label}
      aria-label={label}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
    >
      {uninstall ? "✕" : "↩"}
    </button>
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
  live,
  reversed,
  onPickLine,
  onTakeBack,
  whatIf,
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
  // take a queued line ("program") or a permanent ("field") back into the hand
  onTakeBack: (zone: "program" | "field", index: number) => void;
  // while a hand card is aimed at a line: what every line would come out with
  whatIf: (number | null)[] | null;
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
    // a div, not a button: the installed permanents carry their own
    // take-back buttons, and the drop target sits under them
    return (
      <div
        data-slot-index={aims ? 0 : undefined}
        className={`program-background${aims ? " is-targetable" : ""}${aims && handHoverSlot === 0 ? " is-drop-target" : ""}`}
        onPointerEnter={() => aims && onPoint(0, true)}
        onPointerLeave={() => aims && onPoint(0, false)}
      >
        <button
          type="button"
          className="background-drop"
          aria-label="Program background"
          disabled={locked || !cardSelected || !aims}
          onClick={(event) => onPlay(0, event.currentTarget.parentElement ?? event.currentTarget)}
        />
        <span className="background-label">bg bus</span>
        {running.map((card, i) => (
          <span
            key={i}
            className={`line-socket is-installed type-${card.type}${card === landing ? " is-landing" : ""}`}
            data-field-card={card === landing ? undefined : card.id}
            title={`${card.name}: ${cardText(card, true)}`}
          >
            <CardTypeIcon type={card.type} />
            <span>{card.name}</span>
            {card !== landing && (
              <TakeBack
                name={card.name}
                disabled={locked}
                uninstall={combat.field_uninstalls?.[i] ?? false}
                onClick={() => onTakeBack("field", i)}
              />
            )}
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
      </div>
    );
  }

  const steps = combat.program_preview?.steps ?? [];
  const boosts = boostsOf(steps, combat.program);
  // what the enemy's program move does to which line, marked on it
  const threats = threatsOf(combat, steps);
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
            const step = card && at >= 0 ? steps[at] : undefined;
            // aiming a card elsewhere: how this line's number would change
            const now = step ? step.dealt || step.block || step.heal : null;
            const then = card && whatIf ? whatIf[line] : null;
            const shift = now !== null && then !== null && then !== now ? { now, then } : null;
            const boost = card ? boosts.get(line) : undefined;
            return (
              <div
                key={line}
                className={`program-line${line === hotLine ? " is-hot" : ""}${running === line ? " is-running" : ""}${spentLines.includes(line) ? " is-spent" : ""}${boost ? " is-boosted" : ""}`}
              >
                {card && threats.get(line) && (
                  <span className="line-threat" title={threats.get(line)!.title}>
                    {threats.get(line)!.text}
                  </span>
                )}
                {boost && (
                  <span
                    className="line-boost"
                    title={`${boost.times > 1 ? `Runs ${boost.times} times` : ""}${boost.times > 1 && boost.looped ? ", and " : ""}${boost.looped ? "a Loop repeats it" : ""}`}
                  >
                    {boost.times > 1 && `×${boost.times}`}
                    {boost.looped && "↺"}
                  </span>
                )}
                <span
                  className={`line-chip${shift ? ` is-shift ${shift.then > shift.now ? "is-up" : "is-down"}` : chip ? ` is-${chip.tone}` : " is-none"}`}
                  title={step?.formula ? `${step.formula}${step.runs > 1 ? `, ${step.runs} times` : ""}` : undefined}
                >
                  {shift ? `${shift.now} → ${shift.then}` : chip?.text}
                </span>
                {running === line && step?.formula && (
                  // the running line spells out how it gets there
                  <span className="line-formula" role="status">
                    {step.formula}
                    {step.runs > 1 && <b> ×{step.runs}</b>}
                  </span>
                )}
                {card && at >= 0 && steps[at].combo && (
                  <span className="line-combo" data-tip-term="Combo" data-tip="A named combo: card types run back to back pay out once per run.">
                    ★ {steps[at].combo}
                  </span>
                )}
                {renderAction(card, line)}
                {card && (
                  <TakeBack name={card.name} disabled={locked} onClick={() => onTakeBack("program", line)} />
                )}
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
