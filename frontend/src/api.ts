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
  | "amplifier"
  | "armor"
  | "recycling"
  | "draw_bonus";

export const PERMANENT_CARD_TYPES: readonly CardType[] = [
  "amplifier",
  "armor",
  "recycling",
  "draw_bonus",
];

export interface Card {
  id: string;
  name: string;
  type: CardType;
  value: number;
  description: string;
}

export interface PlayerState {
  hp: number;
  max_hp: number;
  attack: number;
  gold: number;
  relics: { id: string; name: string; description: string }[];
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
}

export interface PendingCombatView {
  enemy_name: string;
  enemy_attack_name: string;
  enemy_hp: number;
  enemy_max_hp: number;
  hand: HandCardView[];
  field: (Card | null)[];
  player_block: number;
  armor: number;
  draw_count: number;
  discard_count: number;
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

export function playCard(runId: string, handIndex: number, slotIndex: number): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/combat/play-card`, {
    method: "POST",
    body: JSON.stringify({ hand_index: handIndex, slot_index: slotIndex }),
  });
}

export function endCombatTurn(runId: string): Promise<RunView> {
  return request<RunView>(`/runs/${runId}/combat/end-turn`, { method: "POST" });
}
