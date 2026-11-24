import type { NemesisSpec } from "../api";
import { PixelEnemy } from "./PixelEnemy";

// On the title screen: last run's killer is waiting (nemesis.ts). Drawn as it
// will come back - an elite at the top of its budget (agent/budgets.py:
// elite attack 13, HP around the middle), named as it will be in the fight.
const ELITE_LOOK = { maxHp: 70, attack: 13 };

export function NemesisHint({ nemesis, setting }: { nemesis: NemesisSpec; setting: string }) {
  const name = `Returned ${nemesis.name}`;
  return (
    <aside className="nemesis-hint" aria-label="Nemesis">
      <span className="nemesis-hint-art">
        <PixelEnemy
          className="nemesis-hint-sprite"
          scale={2}
          spec={{
            name,
            setting,
            bodyShape: nemesis.body_shape ?? undefined,
            feature: nemesis.feature ?? undefined,
            ...ELITE_LOOK,
          }}
        />
      </span>
      <span className="nemesis-hint-text">
        <span className="nemesis-hint-tag">Nemesis</span>
        <span>
          <b>{nemesis.name}</b> is waiting for you.
        </span>
        <small>It killed you last run and returns as the first elite.</small>
      </span>
    </aside>
  );
}
