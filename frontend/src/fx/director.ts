import type { Card, HandCardView, PendingCombatView } from "../api";
import {
  SPOT,
  beam,
  bluescreen,
  bolt,
  comboLabel,
  flash,
  floatNumber,
  glitchBands,
  hitFlash,
  impact,
  shake,
  shield,
  toViewport,
} from "./arena";
import { clamp } from "./motion";
import { burst, risingCode } from "./particles";
import {
  bootSlot,
  crumbleField,
  dealIn,
  dissolveToPile,
  flyToPile,
  handCardEl,
  pileEl,
  pulseSlot,
  slotEls,
  snapshotCard,
  streamFrom,
  type CardGhost,
} from "./table";

// Turns what changed between two server states into effects. The server
// only ever sends the new state, so the director compares it with the last
// one, reads the new history lines for the details (how many hits, how much
// was blocked) and remembers which card the player just played.

export interface CombatSnapshot {
  enemyName: string;
  enemyHp: number;
  enemyBlock: number;
  playerHp: number;
  hand: HandCardView[];
  field: (Card | null)[];
  logLength: number;
}

export function snapshotOf(combat: PendingCombatView, playerHp: number, logLength: number): CombatSnapshot {
  return {
    enemyName: combat.enemy_name,
    enemyHp: combat.enemy_hp,
    enemyBlock: combat.enemy_block,
    playerHp,
    hand: combat.hand,
    field: combat.field,
    logLength,
  };
}

export interface CombatContext {
  boss: boolean;
}

interface PendingPlay {
  card: Card;
  slotIndex: number;
  at: number;
  ghost: CardGhost | null;
  slotRect: DOMRect | null;
  // hand and field as they looked when the card was played, for cards that
  // are gone by the time the answer arrives (discarded, destroyed)
  hand: Map<number, CardGhost>;
  field: CardGhost[];
}

let pending: PendingPlay | null = null;

// Called the moment a card is played (before Dr. Chronos types it in).
export function cardPlayed(card: Card, fromEl: HTMLElement | null, toEl: HTMLElement | null): void {
  const panel = (fromEl ?? toEl)?.closest<HTMLElement>(".combat-panel") ?? null;
  const hand = new Map<number, CardGhost>();
  const field: CardGhost[] = [];
  if (panel) {
    panel.querySelectorAll<HTMLElement>(".hand [data-hand-index]").forEach((el) => {
      hand.set(Number(el.dataset.handIndex), snapshotCard(el));
    });
    if (card.type === "final_strike") {
      for (const slot of slotEls(panel)) {
        if (slot.classList.contains("is-occupied")) field.push(snapshotCard(slot));
      }
    }
  }
  const slotIndex = toEl && panel ? slotEls(panel).indexOf(toEl) : -1;
  pending = {
    card,
    slotIndex,
    at: performance.now(),
    ghost: fromEl ? snapshotCard(fromEl) : null,
    slotRect: toEl?.getBoundingClientRect() ?? null,
    hand,
    field,
  };
}

// ---- log parsing ----------------------------------------------------------

function num(match: RegExpMatchArray | null, group: number): number {
  return match && match[group] !== undefined ? Number(match[group]) : 0;
}

// Splits `damage` per hit against the enemy's block, like the server does:
// what each hit took off the block and what got through.
function hitsAgainstBlock(hits: number, damage: number, block: number) {
  const result: { absorbed: number; dealt: number }[] = [];
  let left = block;
  for (let i = 0; i < hits; i++) {
    const absorbed = Math.min(left, damage);
    left -= absorbed;
    result.push({ absorbed, dealt: damage - absorbed });
  }
  return result;
}

// ---- the reactions --------------------------------------------------------

const IMPACT_MS = 540; // the arena's own enemy hit animation starts at 0.5s

function enemyHits(
  stage: HTMLElement,
  panel: HTMLElement,
  hits: { absorbed: number; dealt: number }[],
  { start = IMPACT_MS, gap = 150, size = 1, crit = false, shot = true }: { start?: number; gap?: number; size?: number; crit?: boolean; shot?: boolean } = {},
) {
  let total = 0;
  const blocked = hits.reduce((sum, h) => sum + h.absorbed, 0);
  if (blocked > 0) shield(stage, "enemy", { delay: start - 300, shatter: hits.some((h) => h.dealt > 0) });
  hits.forEach((hit, i) => {
    const at = start + i * gap;
    const damage = hit.dealt + hit.absorbed;
    total += hit.dealt;
    if (shot) bolt(stage, SPOT.rift, { x: SPOT.enemy.x + (i % 2 ? 1.5 : -1.5), y: SPOT.enemy.y + (i - 1) * 3 }, { delay: at - 150, size });
    impact(stage, { x: SPOT.enemy.x - 3 + i * 1.5, y: SPOT.enemy.y - 4 + (i % 3) * 4 }, { delay: at, size: size * (0.8 + Math.min(damage, 20) / 25) });
    hitFlash(stage, "enemy", { delay: at, strength: size });
    if (hit.absorbed > 0) floatNumber(stage, "enemy", `-${hit.absorbed}`, "shielded", { delay: at, index: i });
    if (hit.dealt > 0 || hit.absorbed === 0) {
      floatNumber(stage, "enemy", `-${hit.dealt}`, crit ? "crit" : "damage", { delay: at + (hit.absorbed ? 90 : 0), index: i });
    }
    const intensity = crit ? 1.4 : clamp(damage / 18, 0.12, 0.9) * size;
    shake(intensity >= 1 ? panel : stage, intensity, at);
  });
  if (hits.length > 1) comboLabel(stage, "enemy", hits.length, total, start + hits.length * gap + 60);
}

function reactToPlay(
  panel: HTMLElement,
  stage: HTMLElement,
  play: PendingPlay,
  before: CombatSnapshot,
  after: CombatSnapshot,
  line: string,
) {
  const { card } = play;
  const slots = slotEls(panel);

  if (card.type === "attack") {
    const m = line.match(/dealing (?:(\d+)x )?(\d+) damage/);
    const hits = Math.max(1, num(m, 1));
    const damage = num(m, 2);
    const split = hitsAgainstBlock(hits, damage, before.enemyBlock);
    if (card.id.startsWith("zero-day")) {
      beam(stage, SPOT.rift, SPOT.enemy, IMPACT_MS - 140);
      flash(stage, "white", { delay: IMPACT_MS, strength: 0.7 });
      glitchBands(stage, { delay: IMPACT_MS, count: 4 });
      enemyHits(stage, panel, split, { size: 2.2, crit: true, shot: false });
    } else if (card.id.startsWith("botnet") && after.field.some(Boolean)) {
      // the drones launch from every permanent on the field
      const sources = slots.filter((_, i) => after.field[i] !== null);
      const target = toViewport(stage, SPOT.enemy);
      streamFrom(sources, target, { color: "#ffb36b", perSlot: 10, delay: 150, drone: true });
      enemyHits(stage, panel, split, { start: 750 + sources.length * 60, shot: false });
    } else {
      enemyHits(stage, panel, split, { gap: hits > 2 ? 120 : 170 });
    }
  } else if (card.type === "final_strike") {
    const m = line.match(/destroying (\d+) permanent card\(s\) for (\d+) damage/);
    const destroyed = num(m, 1);
    const damage = num(m, 2);
    crumbleField(play.field, pileEl(panel, "banished"), 120);
    bluescreen(stage, before.enemyName, 320);
    shake(panel, destroyed > 0 ? 2 : 0.6, 380);
    if (destroyed > 0) {
      flash(stage, "white", { delay: 1150, strength: 0.9 });
      enemyHits(stage, panel, hitsAgainstBlock(1, damage, before.enemyBlock), { start: 1150, size: 2.6, crit: true, shot: false });
    } else {
      floatNumber(stage, "enemy", "0", "damage", { delay: 1150 });
    }
  } else if (card.type === "block") {
    const gained = num(line.match(/gaining (\d+) block/), 1);
    shield(stage, "player", { delay: 150 });
    floatNumber(stage, "player", `+${gained}`, "block", { delay: 250 });
  } else if (card.type === "heal") {
    const healed = after.playerHp - before.playerHp;
    risingCode(toViewport(stage, { x: SPOT.player.x, y: SPOT.player.y + 12 }), { spread: 70 });
    flash(stage, "green", { strength: 0.35 });
    floatNumber(stage, "player", `+${healed}`, "heal", { delay: 250 });
  } else if (play.slotIndex >= 0 && after.field[play.slotIndex]) {
    bootSlot(slots[play.slotIndex], card.name.toLowerCase().replace(/\s+/g, "_"));
  }

  // where the played card itself goes
  if (play.ghost && play.slotRect && after.field[play.slotIndex] == null) {
    if (card.exhaust) dissolveToPile(play.ghost, play.slotRect, pileEl(panel, "banished"));
    else if (/recycled straight back/.test(line)) flyToPile(play.ghost, play.slotRect, pileEl(panel, "deck"), 250);
    else flyToPile(play.ghost, play.slotRect, pileEl(panel, "graveyard"), 250);
  }

  // cards lost to a discard cost (Brute Force, Memory Dump, ...)
  if (/^You discard /.test(line)) {
    const kept = new Set(after.hand.map((c) => c.id));
    before.hand.forEach((c) => {
      const ghost = play.hand.get(c.hand_index);
      if (c.id !== card.id && !kept.has(c.id) && ghost) {
        flyToPile(ghost, ghost.rect, pileEl(panel, "graveyard"), 60, "rgba(198, 90, 58, 0.8)");
      }
    });
  }
}

function reactToEndTurn(panel: HTMLElement, stage: HTMLElement, before: CombatSnapshot, lines: string[], ctx: CombatContext) {
  const slots = slotEls(panel);
  const text = lines.join("\n");
  let t = 0;

  const daemon = text.match(/daemons hit .+? for (\d+) damage(?: \((\d+) blocked\))?/);
  if (daemon) {
    const turrets = slots.filter((_, i) => before.field[i]?.type === "turret");
    turrets.forEach((slot, i) => pulseSlot(slot, "rgba(255, 154, 77, 0.9)", i * 120));
    streamFrom(turrets, toViewport(stage, SPOT.enemy), { color: "#ff9a4d", perSlot: 5 });
    const dealt = num(daemon, 1);
    const absorbed = num(daemon, 2);
    enemyHits(stage, panel, [{ dealt, absorbed }], { start: 600, shot: false });
    t = 700;
  }

  const mainframe = text.match(/mainframe raises (\d+) block/);
  if (mainframe) {
    const forts = slots.filter((_, i) => before.field[i]?.type === "fortify");
    forts.forEach((slot, i) => pulseSlot(slot, "rgba(79, 216, 224, 0.9)", t + i * 120));
    streamFrom(forts, toViewport(stage, SPOT.playerShield), { color: "#4fd8e0", perSlot: 6, delay: t });
    shield(stage, "player", { delay: t + 450 });
    floatNumber(stage, "player", `+${num(mainframe, 1)}`, "block", { delay: t + 500 });
    t += 400;
  }

  const brace = text.match(/braces itself, gaining (\d+) block/);
  if (brace) {
    shield(stage, "enemy", { delay: t + 200 });
    floatNumber(stage, "enemy", `+${num(brace, 1)}`, "block", { delay: t + 300 });
  }

  const blockedHit = text.match(/ uses .+?\. You block (\d+)(?: \(includes \d+ armor\))? and take (\d+) damage/);
  const plainHit = blockedHit ? null : text.match(/ uses .+? for (\d+) damage\. You are at/);
  if (blockedHit || plainHit) {
    const blocked = blockedHit ? num(blockedHit, 1) : 0;
    const taken = blockedHit ? num(blockedHit, 2) : num(plainHit, 1);
    // the arena's own enemy lunge/beam reaches Dr. Chronos about here
    const at = Math.max(t, 0) + 420;
    const heavy = ctx.boss ? 1.8 : 1;
    if (blocked > 0) {
      shield(stage, "player", { delay: at - 280, shatter: true });
      floatNumber(stage, "player", `-${blocked}`, "shielded", { delay: at });
    }
    if (taken > 0) {
      impact(stage, { x: SPOT.player.x + 3, y: SPOT.player.y - 6 }, { delay: at, size: clamp(taken / 10, 0.6, 1.8), color: "red" });
      hitFlash(stage, "player", { delay: at, strength: clamp(taken / 12, 0.4, 1.2) });
      floatNumber(stage, "player", `-${taken}`, ctx.boss ? "crit" : "damage", { delay: at + (blocked ? 100 : 0), index: blocked ? 1 : 0 });
      const intensity = clamp(taken / 14, 0.2, 1) * heavy;
      shake(intensity >= 1 ? panel : stage, intensity, at);
      if (ctx.boss) {
        flash(stage, "red", { delay: at, strength: 0.9 });
        glitchBands(stage, { delay: at, count: 6, color: "rgba(255, 77, 106, 0.4)" });
      } else if (taken >= 10) {
        flash(stage, "red", { delay: at, strength: 0.5 });
      }
    } else {
      shake(stage, 0.15, at);
    }
    t = at;
  }
  return t;
}

export function reactToCombat(
  panel: HTMLElement,
  before: CombatSnapshot,
  after: CombatSnapshot,
  lines: string[],
  ctx: CombatContext,
): void {
  const stage = panel.querySelector<HTMLElement>(".arena-stage");
  if (!stage) return;
  const play = pending;
  pending = null;
  const playLine = play && performance.now() - play.at < 10_000 ? lines.find((l) => l.includes(`You play ${play.card.name}`)) : undefined;

  let dealDelay = 0;
  let dealFrom: "deck" | "graveyard" | "banished" = "deck";
  if (play && playLine !== undefined) {
    reactToPlay(panel, stage, play, before, after, playLine);
    if (play.card.type === "retrieve") dealFrom = "graveyard";
    if (play.card.type === "restore") dealFrom = "banished";
    dealDelay = play.card.type === "draw" ? 150 : 250;
  } else {
    dealDelay = reactToEndTurn(panel, stage, before, lines, ctx) + 450;
  }

  // cards new to the hand fly in from where they came from
  const had = new Set(before.hand.map((c) => c.id));
  const fresh = after.hand
    .filter((c) => !had.has(c.id))
    .map((c) => handCardEl(panel, c.hand_index))
    .filter((el): el is HTMLElement => el !== null);
  if (fresh.length) dealIn(fresh, pileEl(panel, dealFrom), { rewind: dealFrom !== "deck", delay: dealDelay });
}

// A fight begins: the opening hand is dealt from the deck.
export function combatStarted(panel: HTMLElement): void {
  const cards = [...panel.querySelectorAll<HTMLElement>(".hand [data-hand-index]")];
  dealIn(cards, pileEl(panel, "deck"), { delay: 350 });
}

// The killing blow landed: the arena's death animation gets a shake and a
// shower of voxels on top (timed to its CSS: collapse at 1.05s, flash 1.65s).
export function enemyDefeated(panel: HTMLElement): void {
  const stage = panel.querySelector<HTMLElement>(".arena-stage");
  if (!stage) return;
  glitchBands(stage, { delay: 1050, count: 7 });
  shake(panel, 1.1, 1650);
  window.setTimeout(() => {
    const at = toViewport(stage, { x: SPOT.enemy.x, y: SPOT.enemy.y + 8 });
    burst(at, { count: 60, colors: ["#e6fcff", "#8ff2ef", "#4fd8e0", "#1a2e3e", "#ff4d6a"], speed: 520, size: 7, gravity: 420 });
  }, 1650);
  flash(stage, "white", { delay: 1650, strength: 0.6 });
}
