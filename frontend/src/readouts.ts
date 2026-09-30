import type { CardType } from "./api";

// what a card's readout number counts, per card type
const UNIT: Partial<Record<CardType, string>> = {
  attack: "dmg",
  final_strike: "dmg",
  block: "block",
  heal: "hp",
};

export function unitOf(type: CardType): string | undefined {
  return UNIT[type];
}

// "7" for a sure number, "8–13" for a roll
export function rangeText(min: number, max: number): string {
  return min === max ? `${min}` : `${min}–${max}`;
}
