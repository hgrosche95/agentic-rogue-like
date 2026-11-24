// The bestiary: every enemy the player has met, kept in this browser across
// runs. One entry per name and setting - meeting the same enemy again in the
// same world adds to its counts instead of a second entry. Storage can be
// blocked (private mode) or hold garbage: every access is guarded, and a
// broken store simply reads as empty.

import type { PendingCombatView } from "./api";
import type { BodyShape, Feature } from "./components/enemyShape";

export interface BestiaryEntry {
  name: string;
  description: string;
  maxHp: number;
  attack: number;
  attackName: string;
  setting: string;
  // move names seen in its fights (its attack's name included)
  moves: string[];
  bodyShape: BodyShape | null;
  feature: Feature | null;
  finalBoss: boolean;
  encounters: number;
  defeated: number;
  kills: number;
  lastSeen: number;
}

const ENTRIES_KEY = "agentic-rogue-like:bestiary";
// which fights were already counted (and how they ended), so a reload or a
// second update of the same fight never counts it twice
const FIGHTS_KEY = "agentic-rogue-like:bestiary-fights";

export const MAX_ENTRIES = 300;
const MAX_FIGHTS = 200;
const MAX_MOVES = 12;

type FightMark = "seen" | "won" | "lost";

function read<T>(key: string, fallback: T, valid: (value: unknown) => value is T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const value: unknown = JSON.parse(raw);
    return valid(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // blocked or full - the bestiary just doesn't grow this time
  }
}

function isEntry(value: unknown): value is BestiaryEntry {
  if (typeof value !== "object" || value === null) return false;
  const e = value as Record<string, unknown>;
  return (
    typeof e.name === "string" &&
    typeof e.setting === "string" &&
    typeof e.maxHp === "number" &&
    typeof e.attack === "number" &&
    Array.isArray(e.moves)
  );
}

const isEntryList = (value: unknown): value is BestiaryEntry[] => Array.isArray(value);
const isFightMap = (value: unknown): value is Record<string, FightMark> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function loadBestiary(): BestiaryEntry[] {
  return read(ENTRIES_KEY, [], isEntryList).filter(isEntry);
}

function settingKey(setting: string): string {
  return setting.trim().toLowerCase();
}

function entryKey(name: string, setting: string): string {
  return `${settingKey(setting)}|${name}`;
}

// the least recently seen fall out first once the bestiary is full
function save(entries: BestiaryEntry[]) {
  const kept = [...entries].sort((a, b) => b.lastSeen - a.lastSeen).slice(0, MAX_ENTRIES);
  write(ENTRIES_KEY, kept);
}

function loadFights(): Record<string, FightMark> {
  return read(FIGHTS_KEY, {}, isFightMap);
}

function saveFights(fights: Record<string, FightMark>) {
  const ids = Object.keys(fights);
  // insertion order: the oldest fights go first
  const kept = ids.slice(Math.max(0, ids.length - MAX_FIGHTS));
  write(FIGHTS_KEY, Object.fromEntries(kept.map((id) => [id, fights[id]])));
}

function moveNames(combat: PendingCombatView): string[] {
  return [combat.enemy_attack_name, combat.enemy_intent_name].filter(
    (name): name is string => typeof name === "string" && name.trim() !== "",
  );
}

// A fight is on: add the enemy, or update it. Called on every update of the
// fight - the counts move once per fight, the move names it shows are
// collected as they come.
export function noteEncounter(fightId: string, combat: PendingCombatView, setting: string) {
  const entries = loadBestiary();
  const fights = loadFights();
  const key = entryKey(combat.enemy_name, setting);
  const index = entries.findIndex((e) => entryKey(e.name, e.setting) === key);
  const known = index >= 0 ? entries[index] : null;
  const firstUpdate = !(fightId in fights);
  const moves = [...(known?.moves ?? [])];
  for (const name of moveNames(combat)) {
    if (!moves.includes(name) && moves.length < MAX_MOVES) moves.push(name);
  }
  if (!firstUpdate && known && moves.length === known.moves.length) return;
  const entry: BestiaryEntry = {
    name: combat.enemy_name,
    description: combat.enemy_description || known?.description || "",
    maxHp: combat.enemy_max_hp,
    attack: combat.enemy_attack,
    attackName: combat.enemy_attack_name,
    setting: known?.setting ?? setting,
    moves,
    bodyShape: combat.enemy_body_shape ?? known?.bodyShape ?? null,
    feature: combat.enemy_feature ?? known?.feature ?? null,
    finalBoss: combat.final_boss,
    encounters: (known?.encounters ?? 0) + (firstUpdate ? 1 : 0),
    defeated: known?.defeated ?? 0,
    kills: known?.kills ?? 0,
    lastSeen: Date.now(),
  };
  if (index >= 0) entries[index] = entry;
  else entries.push(entry);
  save(entries);
  if (firstUpdate) {
    fights[fightId] = "seen";
    saveFights(fights);
  }
}

// The fight is over: the enemy was beaten, or it killed the player. Counted
// once per fight.
export function noteOutcome(fightId: string, enemyName: string, setting: string, outcome: "won" | "lost") {
  const fights = loadFights();
  if (fights[fightId] === "won" || fights[fightId] === "lost") return;
  const entries = loadBestiary();
  const key = entryKey(enemyName, setting);
  const entry = entries.find((e) => entryKey(e.name, e.setting) === key);
  if (!entry) return;
  if (outcome === "won") entry.defeated += 1;
  else entry.kills += 1;
  entry.lastSeen = Date.now();
  save(entries);
  fights[fightId] = outcome;
  saveFights(fights);
}
