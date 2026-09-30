// Types mirror the Pydantic response models in src/agentic_rogue_like/api.py -
// keep the two in sync by hand for now, there's no shared schema generation yet.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
  | "fortify";

export const PERMANENT_CARD_TYPES: readonly CardType[] = [
  "amplifier",
  "armor",
  "draw_bonus",
  "damage_boost",
  "turret",
  "fortify",
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
}

// A passive bonus for the rest of the run. Only the text is shown - the
// numbers behind it are applied server-side (see artifacts.py).
export interface Artifact {
  id: string;
  name: string;
  description: string;
}

export interface PlayerState {
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
}

export type EnemyIntentType = "attack" | "defend";

export interface PendingCombatView {
  enemy_name: string;
  enemy_attack_name: string;
  enemy_hp: number;
  enemy_max_hp: number;
  enemy_block: number;
  enemy_intent: EnemyIntentType;
  enemy_intent_value: number;
  // the attack's d6 range, and what of it gets through block and armor if
  // the turn ended now (both 0 while the enemy defends)
  enemy_intent_min: number;
  enemy_intent_max: number;
  incoming_min: number;
  incoming_max: number;
  hand: HandCardView[];
  field: (Card | null)[];
  player_block: number;
  armor: number;
  max_hand_size: number;
  draw_count: number;
  discard_count: number;
  banished_count: number;
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
export interface ShopView {
  cards: ShopCard[];
  artifacts: ShopArtifact[];
}

export interface RunView {
  run_id: string;
  status: RunStatus;
  floor: number;
  setting: string;
  player: PlayerState;
  history: string[];
  current_node: MapNode;
  node_resolved: boolean;
  available_choices: MapNode[];
  pending_event: PendingEventView | null;
  pending_combat: PendingCombatView | null;
  card_reward: Card[] | null;
  artifact_offer: Artifact[] | null;
  shop: ShopView | null;
  nodes: Record<string, MapNode>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status} ${body}`);
  }
  return response.json() as Promise<T>;
}

export function listSettings(): Promise<string[]> {
  return request<string[]>("/settings");
}

export function createRun(setting: string, seed?: number): Promise<RunView> {
  return request<RunView>("/runs", {
    method: "POST",
    body: JSON.stringify({ seed: seed ?? null, setting }),
  });
}

export function resolveCurrentNode(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/resolve`, { method: "POST" });
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

export function leaveShop(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/shop/leave`, { method: "POST" });
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
