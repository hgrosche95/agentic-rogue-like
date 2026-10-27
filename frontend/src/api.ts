// Types mirror the Pydantic response models in src/agentic_rogue_like/api.py -
// keep the two in sync by hand for now, there's no shared schema generation yet.

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type RunStatus = "ongoing" | "victory" | "defeat";
export type NodeType = "combat" | "elite" | "event" | "shop" | "rest" | "boss";
export type CardType =
  | "attack"
  | "block"
  | "heal"
  | "final_strike"
  | "draw"
  | "retrieve"
  | "restore"
  | "reboot"
  | "amplifier"
  | "armor"
  | "draw_bonus"
  | "damage_boost"
  | "turret"
  | "fortify"
  // the Vibe-Coder's cards
  | "compact"
  | "free_play"
  | "chain"
  | "token_regen"
  | "safeguard"
  | "opener"
  // junk an enemy's corrupt move shuffles in
  | "glitch"
  // control flow - program mode only
  | "fork"
  | "loop"
  | "if_wounded"
  // the Vibe-Coder's control flow
  | "pipe"
  | "batch";

export const PERMANENT_CARD_TYPES: readonly CardType[] = [
  "amplifier",
  "armor",
  "draw_bonus",
  "damage_boost",
  "turret",
  "fortify",
  "chain",
  "token_regen",
  "safeguard",
  "opener",
];

// Program mode: what queues into the program instead of resolving on the
// spot (combat.QUEUED_TYPES), and the control flow among it.
export const CONTROL_FLOW_TYPES: readonly CardType[] = ["fork", "loop", "if_wounded", "pipe", "batch"];
export const QUEUED_TYPES: readonly CardType[] = [
  "attack",
  "block",
  "heal",
  "final_strike",
  ...CONTROL_FLOW_TYPES,
];

export type Rarity = "starter" | "common" | "uncommon" | "rare";

export interface Card {
  id: string;
  name: string;
  type: CardType;
  value: number;
  description: string;
  rarity: Rarity;
  // one-shot: banished for the rest of the fight after it is played
  exhaust: boolean;
  // attacks only: the damage is dealt this many times
  hits: number;
  // scaling attacks: the bonus per permanent / graveyard / banished card
  scale_value: number;
  // a status it puts on the enemy, and how much (stacks or turns)
  applies: Status | null;
  applies_amount: number;
  // reworked once at a safehouse - its name carries a "+"
  upgraded: boolean;
  // what it takes from a context window - only the Vibe-Coder has one
  token_cost: number;
}

// Who a run is played as - see characters.py.
export type Character = "chronos" | "vibe_coder";

export interface CharacterView {
  id: Character;
  name: string;
  title: string;
  description: string;
  hp: number;
  // tokens per context window, null for characters without one
  token_limit: number | null;
}

// A passive bonus for the rest of the run. Only the text is shown - the
// numbers behind it are applied server-side (see artifacts.py).
export interface Artifact {
  id: string;
  name: string;
  description: string;
  // program mode: the line (1-based) whose card runs upgraded - 0 if none
  hot_path: number;
}

export interface PlayerState {
  character: Character;
  hp: number;
  max_hp: number;
  attack: number;
  gold: number;
  artifacts: Artifact[];
  deck: Card[];
}

export interface MapNode {
  id: string;
  floor: number;
  type: NodeType;
  connections: string[];
  visited: boolean;
}

export interface EventOptionView {
  index: number;
  label: string;
  // what it does in game terms, e.g. "+50 gold, -6 HP" - the price is visible up front
  effects: string;
}

export interface PendingEventView {
  description: string;
  options: EventOptionView[];
}

export interface HandCardView extends Card {
  hand_index: number;
  // what the card comes out with in each field slot (damage per hit, block,
  // healing) - null for occupied slots and cards without such a number
  preview: (number | null)[];
  // playing it now would push past the context window - it may hallucinate
  overflows: boolean;
}

// attack/defend for every enemy, the rest only for bosses
export type EnemyIntentType =
  | "attack"
  | "defend"
  | "barrage"
  | "charge"
  | "overload"
  | "purge"
  | "infect"
  | "lock"
  | "corrupt"
  // program mode: cuts the program off after a few lines
  | "interrupt"
  // program mode, bosses: the program runs right to left
  | "refactor";

// How the player plays, read from their chosen cards - see style.py.
export type PlayStyle = "permanents" | "graveyard" | "one_shot" | "aggro" | "turtle" | "malware" | "program";

// Lasting effects on either side of a fight - see models.Status.
export type Status = "malware" | "exposed" | "throttled";

// intents that hit the player
export const ATTACKING_INTENTS: EnemyIntentType[] = [
  "attack",
  "barrage",
  "overload",
  "purge",
  "infect",
  "lock",
  "corrupt",
  "interrupt",
  "refactor",
];

export interface PendingCombatView {
  enemy_name: string;
  // one line of flavor text, may be empty
  enemy_description: string;
  enemy_attack_name: string;
  // the base attack stat - what the enemy's look is built from
  enemy_attack: number;
  enemy_hp: number;
  enemy_max_hp: number;
  enemy_block: number;
  enemy_intent: EnemyIntentType;
  // program mode: an interrupt lets this many queued lines run, else null
  enemy_interrupt_after: number | null;
  // the move's own name if its move set gave it one, else null
  enemy_intent_name: string | null;
  enemy_intent_value: number;
  // one hit's range and the number of hits, and what of all of them gets
  // through block and armor if the turn ended now (both 0 while the enemy
  // isn't attacking). For block-raising intents min = max = the block and
  // hits = 0.
  enemy_intent_min: number;
  enemy_intent_max: number;
  enemy_intent_hits: number;
  incoming_min: number;
  incoming_max: number;
  // boss fights: phase 2 starts at half HP, phase 3 (later acts) at a
  // quarter - each adds strength
  boss: boolean;
  enemy_phase: number;
  enemy_phases: number;
  enemy_strength: number;
  // the run's final boss, the AGI itself - drawn with its own sprite
  final_boss: boolean;
  // elites: their affix and what it does, else null; whether rage is on
  enemy_affix: "armored" | "regenerating" | "enraged" | "thorny" | null;
  enemy_affix_description: string | null;
  enemy_enraged: boolean;
  // statuses on either side and their stacks / turns left
  enemy_status: Partial<Record<Status, number>>;
  player_status: Partial<Record<Status, number>>;
  // field slots an enemy's lock has shut for this turn
  locked_slots: number[];
  hand: HandCardView[];
  field: (Card | null)[];
  player_block: number;
  armor: number;
  max_hand_size: number;
  draw_count: number;
  discard_count: number;
  banished_count: number;
  // the character's context window - null (and 0s) for characters without one
  token_limit: number | null;
  tokens_used: number;
  // used tokens freed at the end of the turn
  token_regen: number;
  // Program mode: queued actions per line (may be longer than `field`),
  // which of them will hallucinate, and where the fight will stand once the
  // program has run. Null / empty in a classic run.
  program_mode: boolean;
  program: (Card | null)[];
  program_glitched: boolean[];
  program_preview: ProgramPreview | null;
}

export interface ProgramPreview {
  enemy_hp: number;
  enemy_block: number;
  player_hp: number;
  player_block: number;
  // line by line, in the order they run
  steps: ProgramStep[];
}

// What one queued line does when the program runs (the backend's
// combat.ProgramStep): ran, cut by an interrupt, or skipped (enemy down).
export interface ProgramStep {
  slot: number;
  name: string;
  type: CardType;
  outcome: "ran" | "cut" | "skipped";
  // how often its action ran - a fork's target twice, a loop its repeats
  runs: number;
  damage: number;
  dealt: number;
  block: number;
  heal: number;
  hurt: number;
  enemy_hp: number;
  enemy_block: number;
}

export interface ShopCard {
  card: Card;
  price: number;
  sold: boolean;
}

export interface ShopArtifact {
  artifact: Artifact;
  price: number;
  sold: boolean;
}

// What a black market room sells, until the player leaves it.
// A safehouse: heal, upgrade a card, or remove one - one of the three.
export interface RestUpgrade {
  deck_index: number;
  card: Card;
  upgraded: Card;
}

export interface RestView {
  heal_amount: number;
  upgrades: RestUpgrade[];
  can_remove: boolean;
  min_deck_size: number;
}

export interface ShopView {
  cards: ShopCard[];
  artifacts: ShopArtifact[];
  // removing one card from the deck: once per shop, pricier every time
  removal_price: number;
  removal_used: boolean;
  min_deck_size: number;
}

export interface RunView {
  run_id: string;
  status: RunStatus;
  act: number;
  num_acts: number;
  floor: number;
  setting: string;
  player: PlayerState;
  history: string[];
  current_node: MapNode;
  node_resolved: boolean;
  available_choices: MapNode[];
  // until the room just jumped into is entered: the other rooms that jump
  // could have gone to - chooseNextNode switches to one of them
  switch_choices: MapNode[];
  pending_event: PendingEventView | null;
  pending_combat: PendingCombatView | null;
  card_reward: Card[] | null;
  artifact_offer: Artifact[] | null;
  // program mode for the whole run - card texts read differently there
  program_mode: boolean;
  // the start of the run, after the first artifact: a kit, then the AGI's deal
  kit_offer: StarterKit[] | null;
  agi_deals: AgiDeal[] | null;
  shop: ShopView | null;
  rest: RestView | null;
  // what the AGI has read from the cards the player chose
  play_style: PlayStyle | null;
  style_counts: Partial<Record<PlayStyle, number>>;
  nodes: Record<string, MapNode>;
}

// Runs only live in the API's memory (sessions.py): a restart or an idle
// timeout loses them, and every request for that run answers 404.
export class RunLostError extends Error {
  constructor() {
    super("The server lost this run (it was restarted or idle too long). Start a new one.");
  }
}

// One of the starter kits (starts.py): two cards of one strategy that
// replace basic cards.
export interface StarterKit {
  id: string;
  name: string;
  blurb: string;
  cards: Card[];
}

// One of the AGI's opening deals; `cards` is what taking it adds to the deck,
// `mentions` every card its description names (an upgrade as it will be).
export interface AgiDeal {
  kind: "strip" | "mutate" | "forbidden" | "trojan" | "hotfix" | "bribe";
  name: string;
  description: string;
  cards: Card[];
  mentions: Card[];
}

// The server's answer never arrived (or the network dropped it). The move
// itself may well have gone through, so the caller re-reads the run (getRun)
// instead of trusting its own state - without this the game waited forever.
export class RequestLostError extends Error {
  constructor(what: string) {
    super(`${what} got no answer - the game re-synced with the server.`);
  }
}

// Most moves answer in well under a second; creating a run and entering a
// room may wait on the encounter agent (up to three LLM calls) and a cold start.
const TIMEOUT_MS = 20_000;
const SLOW_TIMEOUT_MS = 90_000;

async function request<T>(path: string, init?: RequestInit, timeoutMs = TIMEOUT_MS): Promise<T> {
  const what = `${init?.method ?? "GET"} ${path}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    // a timeout, or the connection failing outright (fetch's TypeError)
    if (err instanceof TypeError || (err instanceof DOMException && err.name === "TimeoutError")) {
      throw new RequestLostError(what);
    }
    throw err;
  }
  if (!response.ok) {
    const body = await response.text();
    if (response.status === 404 && path.startsWith("/runs/") && body.includes("run not found")) {
      throw new RunLostError();
    }
    throw new Error(`${what} failed: ${response.status} ${body}`);
  }
  return response.json() as Promise<T>;
}

export function ping(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

export function listSettings(): Promise<string[]> {
  return request<string[]>("/settings");
}

export function listCharacters(): Promise<CharacterView[]> {
  return request<CharacterView[]>("/characters");
}

export function getRun(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}`);
}

export function createRun(
  setting: string,
  character: Character,
  programMode = false,
  seed?: number,
): Promise<RunView> {
  return request<RunView>("/runs", {
    method: "POST",
    body: JSON.stringify({ seed: seed ?? null, setting, character, program_mode: programMode }),
  }, SLOW_TIMEOUT_MS);
}

export function resolveCurrentNode(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/resolve`, { method: "POST" }, SLOW_TIMEOUT_MS);
}

export function chooseEventOption(runId: string, optionIndex: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/event-choice`, {
    method: "POST",
    body: JSON.stringify({ option_index: optionIndex }),
  });
}

export function chooseNextNode(runId: string, nodeId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/choose-node`, {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId }),
  });
}

export function chooseCardReward(runId: string, cardIndex: number | null): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/card-reward`, {
    method: "POST",
    body: JSON.stringify({ card_index: cardIndex }),
  });
}

export function chooseKit(runId: string, kitIndex: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/kit`, {
    method: "POST",
    body: JSON.stringify({ kit_index: kitIndex }),
  });
}

// null turns every deal down
export function chooseDeal(runId: string, dealIndex: number | null): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/agi-deal`, {
    method: "POST",
    body: JSON.stringify({ deal_index: dealIndex }),
  });
}

export function chooseArtifact(runId: string, artifactIndex: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/artifact`, {
    method: "POST",
    body: JSON.stringify({ artifact_index: artifactIndex }),
  });
}

export function buyShopCard(runId: string, index: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/shop/buy-card`, {
    method: "POST",
    body: JSON.stringify({ index }),
  });
}

export function buyShopArtifact(runId: string, index: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/shop/buy-artifact`, {
    method: "POST",
    body: JSON.stringify({ index }),
  });
}

// `index` is the card's position in the deck (player.deck)
export function removeShopCard(runId: string, index: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/shop/remove-card`, {
    method: "POST",
    body: JSON.stringify({ index }),
  });
}

export function leaveShop(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/shop/leave`, { method: "POST" });
}

export function restHeal(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/rest/heal`, { method: "POST" });
}

export function restUpgrade(runId: string, index: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/rest/upgrade`, {
    method: "POST",
    body: JSON.stringify({ index }),
  });
}

export function restRemove(runId: string, index: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/rest/remove`, {
    method: "POST",
    body: JSON.stringify({ index }),
  });
}

export function playCard(runId: string, handIndex: number, slotIndex: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/combat/play-card`, {
    method: "POST",
    body: JSON.stringify({ hand_index: handIndex, slot_index: slotIndex }),
  });
}

export function endCombatTurn(runId: string, discardIndices: number[] = []): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/combat/end-turn`, {
    method: "POST",
    body: JSON.stringify({ discard_indices: discardIndices }),
  });
}

// Program mode: move a queued action to another line (swaps with what waits there).
export function moveQueued(runId: string, fromSlot: number, toSlot: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/combat/move-queued`, {
    method: "POST",
    body: JSON.stringify({ from_slot: fromSlot, to_slot: toSlot }),
  });
}
