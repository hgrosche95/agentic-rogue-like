import { useId, type Ref } from "react";

// Enemies are invented by the LLM at runtime, so there is no art to load.
// Instead the monster is drawn from the few fields every enemy has:
//   name    -> seed for body shape, eye count and hue (same name, same monster)
//   max HP  -> overall size
//   attack  -> number and length of spikes and teeth, angry brows when strong
//   setting -> palette and a themed feature (horns, circuits, tentacles, ...)
// It is drawn in the arena's 1920x800 frame so it stacks like the other layers.

type Feature = "horns" | "circuits" | "tentacles" | "fins" | "stripes";

interface Theme {
  hues: number[];
  sat: number;
  light: number;
  glow: string | null;
  feature: Feature;
}

const THEMES: Record<Feature, Theme> = {
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

function themeFor(setting: string): Theme {
  const match = KEYWORDS.find(([pattern]) => pattern.test(setting));
  return THEMES[match ? match[1] : FEATURES[hashString(setting) % FEATURES.length]];
}

function hashString(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h = Math.imul(h ^ value.charCodeAt(i), 16777619);
  }
  return h >>> 0;
}

// mulberry32 - small, deterministic, good enough for a decorative shape.
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

const f = (n: number) => n.toFixed(1);

// Stat ranges of the encounter budgets (agent/budgets.py), early to boss.
const HP_RANGE = [25, 180];
const ATTACK_RANGE = [6, 28];

// Where the monster stands in the 1920x800 arena frame - the spot the old
// robot render occupied (feet at y~708, centred on x~1475).
const ANCHOR_X = 1475;
const ANCHOR_Y = 708;
const SCALE = 3.4;

const INK = "#1a120a";
const BONE = "#f4ecd6";

export function EnemyMonster({
  name,
  maxHp,
  attack,
  setting,
  className,
  ref,
}: {
  name: string;
  maxHp: number;
  attack: number;
  setting: string;
  className?: string;
  ref?: Ref<SVGSVGElement>;
}) {
  const uid = useId().replace(/:/g, "");
  const theme = themeFor(setting);
  const rand = mulberry32(hashString(name));
  const hpT = clamp01((maxHp - HP_RANGE[0]) / (HP_RANGE[1] - HP_RANGE[0]));
  const atkT = clamp01((attack - ATTACK_RANGE[0]) / (ATTACK_RANGE[1] - ATTACK_RANGE[0]));

  // Everything below is drawn in a 200x200 box, feet at y~185.
  const C = 100;
  const R = 62 * (0.72 + hpT * 0.28);
  const hue = theme.hues[Math.floor(rand() * theme.hues.length)] + Math.floor(rand() * 20 - 10);
  const body = `hsl(${hue}, ${theme.sat}%, ${theme.light}%)`;
  const dark = `hsl(${hue}, ${theme.sat}%, ${theme.light - 22}%)`;
  const light = `hsl(${hue}, ${theme.sat}%, ${theme.light + 18}%)`;
  // Body centre, so every size stands on the floor; tentacled ones stand on them.
  const cy = 185 - R * 0.95 - (theme.feature === "tentacles" ? 32 : 0);

  // Body: a smooth blob through bumpy radial points, slightly wider at the bottom.
  const N = 10;
  const pts: [number, number][] = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2 - Math.PI / 2;
    const rr = R * (0.8 + rand() * 0.3) * (i > N * 0.3 && i < N * 0.7 ? 1.08 : 1);
    pts.push([C + Math.cos(a) * rr * (1 + (rand() - 0.5) * 0.1), cy + Math.sin(a) * rr * 0.9]);
  }
  const mid = (p: [number, number], q: [number, number]) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
  const [sx, sy] = mid(pts[0], pts[1]);
  let bodyPath = `M${f(sx)},${f(sy)} `;
  for (let i = 1; i <= N; i++) {
    const p = pts[i % N];
    const [mx, my] = mid(p, pts[(i + 1) % N]);
    bodyPath += `Q${f(p[0])},${f(p[1])} ${f(mx)},${f(my)} `;
  }
  bodyPath += "Z";

  // Spikes along the top: more and longer the harder it hits.
  const spikeCount = 2 + Math.round(atkT * 7);
  const spikeLength = 10 + atkT * 22;
  const spikes = Array.from({ length: spikeCount }, (_, i) => {
    const a = -Math.PI * 0.85 + ((i + 0.5) / spikeCount) * Math.PI * 0.7;
    const w = 0.16;
    const at = (angle: number, rx: number, ry: number) => `${f(C + Math.cos(angle) * rx)},${f(cy + Math.sin(angle) * ry)}`;
    return `M${at(a - w, R * 0.8, R * 0.75)} L${at(a, R * 0.85 + spikeLength, R * 0.8 + spikeLength)} L${at(a + w, R * 0.8, R * 0.75)} Z`;
  });

  const tentacleCount = theme.feature === "tentacles" ? 3 + Math.floor(rand() * 3) : 0;
  const tentacles =
    tentacleCount > 0
      ? Array.from({ length: tentacleCount }, (_, i) => {
          const x = C - R * 0.6 + i * ((R * 1.2) / (tentacleCount - 1));
          const sway = (rand() - 0.5) * 40;
          return `M${f(x)},${f(cy + R * 0.6)} q${f(sway)},25 ${f(-sway * 0.5)},${f(35 + rand() * 10)}`;
        })
      : [];
  const circuits =
    theme.feature === "circuits"
      ? Array.from({ length: 4 }, (_, i) => {
          const y = cy + R * (-0.1 + i * 0.18);
          const x = C - R * 0.5 + rand() * R * 0.3;
          return { x, y, d: `M${f(x)},${f(y)} h${f(15 + rand() * 20)} v8 h${f(10 + rand() * 15)}` };
        })
      : [];
  const barnacles =
    theme.feature === "fins"
      ? Array.from({ length: 4 }, () => ({
          x: C - R * 0.5 + rand() * R,
          y: cy + R * 0.2 + rand() * R * 0.4,
          r: 3 + rand() * 3,
        }))
      : [];

  // Eyes: one to three, aliens get three to five.
  const eyeCount = theme.feature === "tentacles" ? 3 + Math.floor(rand() * 3) : 1 + Math.floor(rand() * 3);
  const eyeY = cy - R * 0.12;
  const spread = R * 0.9;
  const eyes = Array.from({ length: eyeCount }, (_, i) => ({
    x: eyeCount === 1 ? C : C - spread / 2 + (i * spread) / (eyeCount - 1),
    y: eyeY + (eyeCount > 2 && i % 2 ? -8 : 0),
    r: eyeCount === 1 ? 15 : Math.max(6, 13 - eyeCount),
    look: (rand() - 0.5) * 4 - 2, // glance left, towards the player
  }));

  // Mouth and teeth.
  const mouthWidth = R * 0.9;
  const mouthY = cy + R * 0.35;
  const teethCount = 3 + Math.round(atkT * 7);
  const toothLength = 5 + atkT * 9;
  const teeth = Array.from({ length: teethCount }, (_, i) => {
    const x = C - mouthWidth / 2 + ((i + 0.5) * mouthWidth) / teethCount;
    const w = (mouthWidth / teethCount) * 0.4;
    return `M${f(x - w)},${f(mouthY + 1)} L${f(x)},${f(mouthY + toothLength)} L${f(x + w)},${f(mouthY + 1)} Z`;
  });

  const transform = `translate(${f(ANCHOR_X - C * SCALE)} ${f(ANCHOR_Y - 185 * SCALE)}) scale(${SCALE})`;

  return (
    <svg ref={ref} className={className} viewBox="0 0 1920 800" preserveAspectRatio="xMidYMid meet" role="img" aria-label={name}>
      <defs>
        {theme.glow && (
          <filter id={`${uid}-glow`} x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor={theme.glow} floodOpacity="0.7" />
          </filter>
        )}
        <clipPath id={`${uid}-body`}>
          <path d={bodyPath} />
        </clipPath>
      </defs>
      <g transform={transform}>
        <ellipse cx={C} cy={188} rx={R * 0.8} ry={6} fill="#000" opacity={0.35} />
        <g filter={theme.glow ? `url(#${uid}-glow)` : undefined} stroke={INK} strokeLinejoin="round">
          {spikes.map((d) => (
            <path key={d} d={d} fill={dark} strokeWidth={2.5} />
          ))}
          {theme.feature === "horns" &&
            [-1, 1].map((s) => (
              <path
                key={s}
                d={`M${f(C + s * R * 0.45)},${f(cy - R * 0.55)} q${s * 30},-10 ${s * 30},-42 q${-s * 8},20 ${-s * 22},30 Z`}
                fill="#d9ccb0"
                strokeWidth={2.5}
              />
            ))}
          {tentacles.map((d) => (
            <g key={d} fill="none" strokeLinecap="round">
              <path d={d} strokeWidth={12} />
              <path d={d} stroke={dark} strokeWidth={7} />
            </g>
          ))}
          {theme.feature === "fins" &&
            [-1, 1].map((s) => (
              <path key={s} d={`M${f(C + s * R * 0.8)},${f(cy + 5)} l${s * 30},-10 l${-s * 8},30 Z`} fill={light} strokeWidth={2.5} />
            ))}
          <path d={bodyPath} fill={body} strokeWidth={3} />
        </g>
        <g clipPath={`url(#${uid}-body)`}>
          {circuits.map(({ x, y, d }) => (
            <g key={d}>
              <path d={d} fill="none" stroke={theme.glow ?? light} strokeWidth={1.8} opacity={0.8} />
              <circle cx={x} cy={y} r={2} fill={theme.glow ?? light} />
            </g>
          ))}
          {theme.feature === "stripes" &&
            [-3, -2, -1, 0, 1, 2, 3].map((i) => (
              <path key={i} d={`M${f(C + i * 18 - 10)},${f(cy - R)} l30,${f(R * 2.2)}`} stroke={light} strokeWidth={7} opacity={0.45} />
            ))}
          {barnacles.map(({ x, y, r }) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="#e8e0c8" stroke={INK} strokeWidth={1.5} />
          ))}
          <ellipse cx={C - R * 0.3} cy={cy - R * 0.3} rx={R * 0.35} ry={R * 0.2} fill="#fff" opacity={0.12} />
        </g>
        {eyes.map(({ x, y, r, look }) => (
          <g key={x}>
            <circle cx={x} cy={y} r={r} fill={BONE} stroke={INK} strokeWidth={2.5} />
            <circle cx={x + look} cy={y + 2} r={r * 0.45} fill={theme.glow ?? INK} />
          </g>
        ))}
        {atkT >= 0.4 && (
          <path
            d={`M${f(C - spread / 2 - 10)},${f(eyeY - 20)} L${f(C - 6)},${f(eyeY - 10)} M${f(C + spread / 2 + 10)},${f(eyeY - 20)} L${f(C + 6)},${f(eyeY - 10)}`}
            stroke={INK}
            strokeWidth={4}
            strokeLinecap="round"
          />
        )}
        <path
          d={`M${f(C - mouthWidth / 2)},${f(mouthY)} Q${C},${f(mouthY + 22 + atkT * 12)} ${f(C + mouthWidth / 2)},${f(mouthY)} Z`}
          fill="#2a0e0e"
          stroke={INK}
          strokeWidth={2.5}
          strokeLinejoin="round"
        />
        {teeth.map((d) => (
          <path key={d} d={d} fill={BONE} />
        ))}
      </g>
    </svg>
  );
}
