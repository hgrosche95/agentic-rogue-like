// The enemy sprites' themes and stat ranges (see pixel/enemySprite.ts).

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
