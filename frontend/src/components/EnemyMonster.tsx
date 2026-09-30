import { useId, type Ref } from "react";
import {
  ANCHOR_X,
  ANCHOR_Y,
  ATTACK_RANGE,
  HP_RANGE,
  SCALE,
  clamp01,
  hashString,
  mulberry32,
  themeFor,
} from "./enemyShape";

// Enemies are invented by the LLM at runtime, so there is no art to load.
// Instead the monster is drawn from the few fields every enemy has:
//   name    -> seed for body shape, eye count and hue (same name, same monster)
//   max HP  -> overall size
//   attack  -> number and length of spikes and teeth, angry brows when strong
//   setting -> palette and a themed feature (horns, circuits, tentacles, ...)
// It is drawn in the arena's 1920x800 frame so it stacks like the other layers,
// and lit like the rendered scene around it: a soft key from above, the
// rift's cyan as a rim light on the side facing the player, occlusion
// underneath and a blurred contact shadow - no cartoon ink outline.

const f = (n: number) => n.toFixed(1);

const INK = "#140c24";
const BONE = "#f4ecd6";
const RIM = "#8ff2ef";

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
  const deep = `hsl(${hue}, ${theme.sat}%, ${Math.max(theme.light - 36, 6)}%)`;
  const edge = `hsl(${hue}, ${theme.sat}%, ${Math.max(theme.light - 30, 8)}%)`;
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
        {/* key light from the upper left, falling off into the body's shadow side */}
        <radialGradient id={`${uid}-shade`} cx="0.38" cy="0.3" r="0.8">
          <stop offset="0" stopColor={light} />
          <stop offset="0.45" stopColor={body} />
          <stop offset="1" stopColor={deep} />
        </radialGradient>
        {/* the rift's cyan glancing off the side that faces the player */}
        <linearGradient id={`${uid}-rim`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor={RIM} stopOpacity="0.75" />
          <stop offset="0.14" stopColor={RIM} stopOpacity="0.18" />
          <stop offset="0.3" stopColor={RIM} stopOpacity="0" />
        </linearGradient>
        {/* ambient occlusion: the underside sinks into the floor's shadow */}
        <linearGradient id={`${uid}-occlusion`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0.45" stopColor={INK} stopOpacity="0" />
          <stop offset="1" stopColor={INK} stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id={`${uid}-spike`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={light} />
          <stop offset="1" stopColor={deep} />
        </linearGradient>
        <radialGradient id={`${uid}-eye`} cx="0.4" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#fffdf6" />
          <stop offset="0.7" stopColor={BONE} />
          <stop offset="1" stopColor="#b9ae96" />
        </radialGradient>
        <filter id={`${uid}-soft`} x="-50%" y="-200%" width="200%" height="500%">
          <feGaussianBlur stdDeviation="4" />
        </filter>
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
        <ellipse cx={C} cy={188} rx={R * 0.9} ry={7} fill={INK} opacity={0.7} filter={`url(#${uid}-soft)`} />
        <g filter={theme.glow ? `url(#${uid}-glow)` : undefined} stroke={edge} strokeLinejoin="round">
          {spikes.map((d) => (
            <path key={d} d={d} fill={`url(#${uid}-spike)`} strokeWidth={1.2} />
          ))}
          {theme.feature === "horns" &&
            [-1, 1].map((s) => (
              <path
                key={s}
                d={`M${f(C + s * R * 0.45)},${f(cy - R * 0.55)} q${s * 30},-10 ${s * 30},-42 q${-s * 8},20 ${-s * 22},30 Z`}
                fill="#d9ccb0"
                stroke="#6a5a40"
                strokeWidth={1.2}
              />
            ))}
          {tentacles.map((d) => (
            <g key={d} fill="none" strokeLinecap="round">
              <path d={d} strokeWidth={11} />
              <path d={d} stroke={dark} strokeWidth={8} />
            </g>
          ))}
          {theme.feature === "fins" &&
            [-1, 1].map((s) => (
              <path key={s} d={`M${f(C + s * R * 0.8)},${f(cy + 5)} l${s * 30},-10 l${-s * 8},30 Z`} fill={light} strokeWidth={1.2} />
            ))}
          <path d={bodyPath} fill={`url(#${uid}-shade)`} strokeWidth={1.5} />
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
            <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="#e8e0c8" stroke={edge} strokeWidth={1} />
          ))}
          <path d={bodyPath} fill={`url(#${uid}-occlusion)`} />
          <path d={bodyPath} fill={`url(#${uid}-rim)`} style={{ mixBlendMode: "screen" }} />
          {/* a soft specular sheen where the key light hits */}
          <ellipse cx={C - R * 0.3} cy={cy - R * 0.38} rx={R * 0.3} ry={R * 0.14} fill="#fff" opacity={0.22} filter={`url(#${uid}-soft)`} />
        </g>
        {eyes.map(({ x, y, r, look }) => (
          <g key={x}>
            {/* the socket's shadow, then a wet eyeball with a pupil and a glint */}
            <circle cx={x} cy={y + 1.5} r={r + 2} fill={INK} opacity={0.45} />
            <circle cx={x} cy={y} r={r} fill={`url(#${uid}-eye)`} stroke={edge} strokeWidth={1} />
            <circle cx={x + look} cy={y + 2} r={r * 0.45} fill={theme.glow ?? INK} />
            <circle cx={x + look} cy={y + 2} r={r * 0.22} fill={INK} opacity={0.8} />
            <circle cx={x - r * 0.35} cy={y - r * 0.4} r={Math.max(1.5, r * 0.18)} fill="#fff" opacity={0.9} />
          </g>
        ))}
        {atkT >= 0.4 && (
          <path
            d={`M${f(C - spread / 2 - 10)},${f(eyeY - 20)} L${f(C - 6)},${f(eyeY - 10)} M${f(C + spread / 2 + 10)},${f(eyeY - 20)} L${f(C + 6)},${f(eyeY - 10)}`}
            stroke={deep}
            strokeWidth={4}
            strokeLinecap="round"
          />
        )}
        <path
          d={`M${f(C - mouthWidth / 2)},${f(mouthY)} Q${C},${f(mouthY + 22 + atkT * 12)} ${f(C + mouthWidth / 2)},${f(mouthY)} Z`}
          fill="#1e0a14"
          stroke={edge}
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
        {teeth.map((d) => (
          <path key={d} d={d} fill={BONE} />
        ))}
      </g>
    </svg>
  );
}
