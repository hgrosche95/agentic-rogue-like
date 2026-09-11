// Enemies are LLM-generated with arbitrary names ("Neon Wraith", "Grim
// Shard", ...) - there's no fixed art to draw on. Instead, hash the name
// into a jagged silhouette + hue: same name always looks the same, every
// name looks different, no asset pipeline needed.

function hashString(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i++) {
    h = (Math.imul(h, 31) + value.charCodeAt(i)) >>> 0;
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

const SIZE = 64;
const CENTER = SIZE / 2;
const SPIKES = 9;

export function MonsterIcon({ seed, size = 56 }: { seed: string; size?: number }) {
  const hash = hashString(seed);
  const rand = mulberry32(hash);

  const points: string[] = [];
  for (let i = 0; i < SPIKES; i++) {
    const angle = (i / SPIKES) * Math.PI * 2;
    const radius = CENTER * (0.55 + rand() * 0.42);
    const x = CENTER + Math.cos(angle) * radius;
    const y = CENTER + Math.sin(angle) * radius;
    points.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
  }
  const path = `${points.join(" ")} Z`;

  const hue = hash % 360;
  const fill = `hsl(${hue}, 60%, 58%)`;
  const eyeSpread = 5 + (hash % 6);
  const eyeY = CENTER - 2 + (hash % 5);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="monster-icon"
      role="img"
      aria-label={seed}
    >
      <path d={path} fill={fill} stroke="var(--line)" strokeWidth="2.5" strokeLinejoin="round" />
      <circle cx={CENTER - eyeSpread} cy={eyeY} r="3" fill="var(--line)" />
      <circle cx={CENTER + eyeSpread} cy={eyeY} r="3" fill="var(--line)" />
    </svg>
  );
}
