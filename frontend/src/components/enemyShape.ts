// The enemy drawing's themes and size rules, shared by EnemyMonster (which
// draws it) and the arena (which places things relative to it).

export type Feature = "horns" | "circuits" | "tentacles" | "fins" | "stripes";

export interface Theme {
  hues: number[];
  sat: number;
  light: number;
  glow: string | null;
  feature: Feature;
}

export const THEMES: Record<Feature, Theme> = {
  horns: { hues: [20, 90, 0], sat: 35, light: 42, glow: null, feature: "horns" },
  circuits: { hues: [300, 190, 170], sat: 80, light: 45, glow: "#33ffff", feature: "circuits" },
  tentacles: { hues: [110, 150, 270], sat: 60, light: 45, glow: "#b6ff5c", feature: "tentacles" },
  fins: { hues: [195, 175, 210], sat: 50, light: 40, glow: null, feature: "fins" },
  stripes: { hues: [0, 280, 45], sat: 65, light: 48, glow: "#ffe27a", feature: "stripes" },
};

// Presets map directly; free-text settings are matched by keyword and
// otherwise fall back to a theme picked from the setting's hash.
const KEYWORDS: [RegExp, Feature][] = [
  [/dungeon|crypt|castle|medieval|cave|fantasy/i, "horns"],
  [/cyber|neon|robot|digital|future|tech|space ?station/i, "circuits"],
  [/alien|planet|space|swamp|jungle|spore/i, "tentacles"],
  [/pirate|sea|ocean|water|ship|island|beach/i, "fins"],
  [/carnival|circus|haunt|horror|ghost|clown|fair/i, "stripes"],
];

const FEATURES = Object.keys(THEMES) as Feature[];

export function themeFor(setting: string): Theme {
  const match = KEYWORDS.find(([pattern]) => pattern.test(setting));
  return THEMES[match ? match[1] : FEATURES[hashString(setting) % FEATURES.length]];
}

export function hashString(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h = Math.imul(h ^ value.charCodeAt(i), 16777619);
  }
  return h >>> 0;
}

// mulberry32 - small, deterministic, good enough for a decorative shape.
export function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}


// Stat ranges of the encounter budgets (agent/budgets.py), early to boss.
export const HP_RANGE = [38, 130];
export const ATTACK_RANGE = [9, 18];

// Where the monster stands in the 1920x800 arena frame - the spot the old
// robot render occupied (feet at y~708, centred on x~1475).
export const ANCHOR_X = 1475;
export const ANCHOR_Y = 708;
export const SCALE = 3.4;

// The top of the monster's head (spikes and horns included) as a share of
// the arena frame's height - where things are shown "above its head". Uses
// the same size formulas as the drawing below.
export function headTopFraction(maxHp: number, attack: number, setting: string): number {
  const theme = themeFor(setting);
  const hpT = clamp01((maxHp - HP_RANGE[0]) / (HP_RANGE[1] - HP_RANGE[0]));
  const atkT = clamp01((attack - ATTACK_RANGE[0]) / (ATTACK_RANGE[1] - ATTACK_RANGE[0]));
  const R = 62 * (0.72 + hpT * 0.28);
  const cy = 185 - R * 0.95 - (theme.feature === "tentacles" ? 32 : 0);
  const spikeTop = cy - R * 0.8 - (10 + atkT * 22);
  const hornTop = theme.feature === "horns" ? cy - R * 0.55 - 42 : spikeTop;
  const top = Math.min(spikeTop, hornTop);
  return (ANCHOR_Y - 185 * SCALE + top * SCALE) / 800;
}
