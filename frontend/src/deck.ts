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

// The deck with identical cards stacked into one entry with a count, in
// TYPE_ORDER, then by name.
export function stackDeck(deck: Card[]): { card: Card; count: number }[] {
  const stacks = new Map<string, { card: Card; count: number }>();
  for (const card of deck) {
    const stack = stacks.get(card.name);
    if (stack) stack.count += 1;
    else stacks.set(card.name, { card, count: 1 });
  }
  return [...stacks.values()].sort(
    (a, b) =>
      TYPE_ORDER.indexOf(a.card.type) - TYPE_ORDER.indexOf(b.card.type) ||
      a.card.name.localeCompare(b.card.name),
  );
}
