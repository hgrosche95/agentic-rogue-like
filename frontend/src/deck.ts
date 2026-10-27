import type { Card, CardType } from "./api";

// The order cards are listed in: attacks first, then defense, then the
// card-flow and permanent cards.
const TYPE_ORDER: CardType[] = [
  "attack",
  "final_strike",
  "block",
  "heal",
  "draw",
  "retrieve",
  "restore",
  "reboot",
  "amplifier",
  "armor",
  "draw_bonus",
  "damage_boost",
  "turret",
  "fortify",
  "compact",
  "free_play",
  "chain",
  "token_regen",
  "safeguard",
  "opener",
];

// How cards are listed: in TYPE_ORDER, then by name.
function byListOrder(a: Card, b: Card): number {
  return TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type) || a.name.localeCompare(b.name);
}

// The deck with identical cards stacked into one entry with a count, in
// TYPE_ORDER, then by name.
export function stackDeck(deck: Card[]): { card: Card; count: number }[] {
  const stacks = new Map<string, { card: Card; count: number }>();
  for (const card of deck) {
    const stack = stacks.get(card.name);
    if (stack) stack.count += 1;
    else stacks.set(card.name, { card, count: 1 });
  }
  return [...stacks.values()].sort((a, b) => byListOrder(a.card, b.card));
}

// The deck in the same order, but every copy its own entry with its deck
// index - for picking one specific card (upgrade, remove).
export function listDeck(deck: Card[]): { card: Card; index: number }[] {
  return deck.map((card, index) => ({ card, index })).sort((a, b) => byListOrder(a.card, b.card) || a.index - b.index);
}
