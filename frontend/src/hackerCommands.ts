import type { Card } from "./api";

// A command Dr. Chronos typed, placed in front of the history line at `at`
// (the line the played card will produce once the server answers).
// Dr. Chronos types every command in about this long, whatever its length -
// short enough not to stall the fight. The card only resolves once he is done.
export const TYPING_MS = 600;

export function typingInterval(text: string): number {
  return TYPING_MS / Math.max(1, text.length);
}

export interface HackerCommand {
  at: number;
  text: string;
}

function slug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

// The shell command Dr. Chronos "hacks in" for a played card.
export function commandFor(card: Card, enemyName: string): string {
  const target = slug(enemyName) || "target";
  switch (card.type) {
    case "attack":
      return `./exploit --target=${target} --dmg ${card.value}`;
    case "final_strike":
      return `sudo ./kernel_panic --target=${target}`;
    case "block":
      return `firewall --up --block ${card.value}`;
    case "heal":
      return `hotfix --self --hp +${card.value}`;
    case "amplifier":
      return `overclock --atk +${card.value}%`;
    case "armor":
      return `encrypt --armor ${card.value}`;
    case "recycling":
      return `gc --recycle`;
    case "draw_bonus":
      return `prefetch --cards +${card.value}`;
  }
}
