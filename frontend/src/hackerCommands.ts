import type { Card } from "./api";
import { tempoMs } from "./tempo";

// A command Dr. Chronos typed, placed in front of the history line at `at`
// (the line the played card will produce once the server answers).
// Dr. Chronos types every command in about this long, whatever its length -
// short enough not to stall the fight (at the normal tempo, see tempo.ts). The
// card only resolves once he is done.
export const TYPING_MS = 600;

export function typingInterval(text: string): number {
  return tempoMs(TYPING_MS) / Math.max(1, text.length);
}

export interface HackerCommand {
  at: number;
  text: string;
}

function slug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

// The shell command Dr. Chronos "hacks in" for a played card - `banished`:
// the hand cards it banishes (Purge), shredded first.
export function commandFor(card: Card, enemyName: string, banished: string[] = []): string {
  const target = slug(enemyName) || "target";
  if (banished.length > 0) {
    const files = banished.map((name) => `./${slug(name)}`).join(" ");
    return `shred -u ${files} && curl -s ./cards | head -${card.value}`;
  }
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
    case "draw_bonus":
      return `prefetch --cards +${card.value}`;
    case "draw":
      return `curl -s ./cards | head -${card.value}`;
    case "retrieve":
      return `git reset --soft HEAD~${card.value}`;
    case "restore":
      return `undelete --last ${card.value}`;
    case "reboot":
      return `sudo systemctl reboot --restore-all`;
    case "damage_boost":
      return `loadbalance --spread`;
    case "turret":
      return `nohup ./daemon --target=${target} &`;
    case "fortify":
      return `mainframe --harden`;
    case "compact":
      return `/compact`;
    case "chain":
      return `copilot --accept-all`;
    case "token_regen":
      return `crack open ./energy-drink`;
    case "free_play":
      return `<tab> <tab> <tab>`;
    case "safeguard":
      return `explain --to rubber-duck`;
    case "opener":
      return `pair --driver copilot`;
    case "glitch":
      return `rm -f ./glitch.tmp`;
    case "fork":
      return `fork() && fork()`;
    case "loop":
      return `while true; do !!; done`;
    case "pipe":
      return `cat ./queue | xargs`;
    case "batch":
      return `parallel --jobs ${card.value} ./run`;
    case "if_wounded":
      return `[ $${slug(enemyName) || "target"}_hp -le 50 ] &&`;
  }
}
