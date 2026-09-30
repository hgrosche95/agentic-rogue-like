import {
  ATTACK_RANGE,
  HP_RANGE,
  clamp01,
  hashString,
  mulberry32,
  themeFor,
  type Feature,
} from "../components/enemyShape";
import { C, RAMP } from "./palette";

// Enemies are invented by the LLM at runtime, so there is no art to load.
// The sprite is built pixel by pixel from the few fields every enemy has:
//   name    -> seed for body shape, eye count and color ramp
//   max HP  -> overall size
//   attack  -> number and length of spikes and teeth, angry brows when strong
//   setting -> color ramps and a themed feature (horns, circuits, ...)
// Same inputs, same sprite.

export interface EnemySpec {
  name: string;
  maxHp: number;
  attack: number;
  setting: string;
}

export interface EnemySprite {
  w: number;
  h: number;
  // palette index + 1 per pixel, 0 = transparent
  pixels: Uint8Array;
  // top-left of each eye's white, and its size, for blinking
  eyes: { x: number; y: number; s: number }[];
  // first row with a pixel in it
  top: number;
  // the particle ramp of its attacks
  ramp: number;
  // the ramp of its body, dark / mid / light
  body: readonly [number, number, number];
}

const SIZE = 64;
const FEATURES: Feature[] = ["horns", "circuits", "tentacles", "fins", "stripes"];
const ATTACK_RAMP: Record<Feature, number> = {
  horns: RAMP.red,
  circuits: RAMP.magenta,
  tentacles: RAMP.green,
  fins: RAMP.cyan,
  stripes: RAMP.amber,
};

// point-in-triangle by edge signs
function inTriangle(px: number, py: number, ax: number, ay: number, bx: number, by: number, cx: number, cy: number) {
  const d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by);
  const d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy);
  const d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay);
  const neg = d1 < 0 || d2 < 0 || d3 < 0;
  const pos = d1 > 0 || d2 > 0 || d3 > 0;
  return !(neg && pos);
}

const cache = new Map<string, EnemySprite>();

export function enemySprite(spec: EnemySpec): EnemySprite {
  const key = `${spec.name}|${spec.maxHp}|${spec.attack}|${spec.setting}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const sprite = build(spec);
  cache.set(key, sprite);
  return sprite;
}

function build({ name, maxHp, attack, setting }: EnemySpec): EnemySprite {
  const theme = themeFor(setting);
  const rand = mulberry32(hashString(name));
  const hpT = clamp01((maxHp - HP_RANGE[0]) / (HP_RANGE[1] - HP_RANGE[0]));
  const atkT = clamp01((attack - ATTACK_RANGE[0]) / (ATTACK_RANGE[1] - ATTACK_RANGE[0]));
  const rampBase = C.enemyRamps + FEATURES.indexOf(theme.feature) * 6 + (rand() < 0.5 ? 0 : 3);
  const body = [rampBase, rampBase + 1, rampBase + 2] as const;
  const [dark, mid, light] = body;

  const W = SIZE;
  const H = SIZE;
  const px = new Uint8Array(W * H);
  const set = (x: number, y: number, c: number) => {
    if (x >= 0 && y >= 0 && x < W && y < H) px[y * W + x] = c + 1;
  };
  const get = (x: number, y: number) => (x >= 0 && y >= 0 && x < W && y < H ? px[y * W + x] : 0);

  const R = 11 + hpT * 8;
  const cx = W / 2;
  const tentacled = theme.feature === "tentacles";
  const cy = H - 1 - R * 0.92 - (tentacled ? 7 : 0);

  // body outline: bumpy radial points, a little wider at the bottom
  const N = 10;
  const radii: number[] = [];
  for (let i = 0; i < N; i++) {
    const bottom = i > N * 0.3 && i < N * 0.7 ? 1.08 : 1;
    radii.push(R * (0.82 + rand() * 0.28) * bottom);
  }
  const radiusAt = (angle: number) => {
    const f = (((angle + Math.PI / 2) / (Math.PI * 2)) * N + N) % N;
    const i = Math.floor(f);
    const t = (1 - Math.cos((f - i) * Math.PI)) / 2;
    return radii[i] * (1 - t) + radii[(i + 1) % N] * t;
  };
  const inBody = (x: number, y: number) => {
    const dx = x + 0.5 - cx;
    const dy = (y + 0.5 - cy) / 0.9;
    return Math.hypot(dx, dy) <= radiusAt(Math.atan2(dy, dx));
  };

  // spikes along the top: more and longer the harder it hits
  const spikeCount = 2 + Math.round(atkT * 5);
  const spikeLength = 3 + atkT * 6;
  const spikes: number[][] = [];
  for (let i = 0; i < spikeCount; i++) {
    const a = -Math.PI * 0.85 + ((i + 0.5) / spikeCount) * Math.PI * 0.7;
    const w = 0.2;
    const r0 = radiusAt(a) * 0.85;
    spikes.push([
      cx + Math.cos(a - w) * r0,
      cy + Math.sin(a - w) * r0 * 0.9,
      cx + Math.cos(a) * (r0 + spikeLength + 2),
      cy + Math.sin(a) * (r0 + spikeLength + 2) * 0.9,
      cx + Math.cos(a + w) * r0,
      cy + Math.sin(a + w) * r0 * 0.9,
    ]);
  }

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (spikes.some((s) => inTriangle(x + 0.5, y + 0.5, s[0], s[1], s[2], s[3], s[4], s[5]))) {
        set(x, y, (x + y) % 5 === 0 ? mid : dark);
      }
    }
  }

  // horns: two bone-colored crescents
  if (theme.feature === "horns") {
    for (const side of [-1, 1]) {
      const bx = cx + side * R * 0.45;
      const by = cy - R * 0.6;
      for (let t = 0; t <= 1; t += 0.02) {
        const hx = bx + side * (Math.sin(t * 1.4) * 9);
        const hy = by - t * 10 + t * t * 2;
        const thick = Math.max(1, Math.round((1 - t) * 2.5));
        for (let k = 0; k < thick; k++) set(Math.round(hx) + (side > 0 ? -k : k), Math.round(hy), t > 0.7 ? C.coat : C.brassHi);
      }
    }
  }

  // tentacles under the body
  if (tentacled) {
    const count = 3 + Math.floor(rand() * 3);
    for (let i = 0; i < count; i++) {
      const x0 = cx - R * 0.6 + (i * (R * 1.2)) / (count - 1);
      const sway = (rand() - 0.5) * 6;
      for (let y = Math.round(cy + R * 0.5); y < H; y++) {
        const t = (y - (cy + R * 0.5)) / (H - (cy + R * 0.5));
        const x = Math.round(x0 + Math.sin(t * Math.PI) * sway);
        set(x, y, dark);
        set(x + 1, y, t < 0.7 ? mid : dark);
      }
    }
  }

  // fins at the sides
  if (theme.feature === "fins") {
    for (const side of [-1, 1]) {
      const bx = cx + side * R * 0.85;
      for (let y = 0; y < H; y++)
        for (let x = 0; x < W; x++)
          if (inTriangle(x + 0.5, y + 0.5, bx, cy - 2, bx + side * 8, cy - 5, bx + side * 3, cy + 6)) set(x, y, light);
    }
  }

  // the body, lit from the upper left, with the rift's cyan on its left edge
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (!inBody(x, y)) continue;
      const nx = (x + 0.5 - cx) / R;
      const ny = (y + 0.5 - cy) / R;
      const lit = -(nx * 0.55 + ny * 0.8);
      let c: number = lit > 0.35 ? light : lit > -0.35 ? mid : dark;
      // a two-tone dither where the shades meet
      if (lit > 0.3 && lit <= 0.4 && (x + y) % 2 === 0) c = mid;
      if (lit > -0.4 && lit <= -0.3 && (x + y) % 2 === 0) c = dark;
      set(x, y, c);
    }
  }
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (!inBody(x, y) || inBody(x - 1, y)) continue;
      const ny = (y + 0.5 - cy) / R;
      if (ny > -0.7 && ny < 0.6) set(x, y, ny < 0.1 ? C.cyanHi : C.cyan);
    }
  }
  // specular glint
  set(Math.round(cx - R * 0.4), Math.round(cy - R * 0.55), C.white);
  set(Math.round(cx - R * 0.4) + 1, Math.round(cy - R * 0.55), light);

  // theme markings, clipped to the body
  const onBody = (x: number, y: number, c: number) => {
    if (inBody(x, y)) set(x, y, c);
  };
  if (theme.feature === "circuits") {
    const glow = rand() < 0.5 ? C.cyan : C.magentaHi;
    for (let i = 0; i < 3; i++) {
      let x = Math.round(cx - R * 0.6 + rand() * R * 0.3);
      let y = Math.round(cy + R * (0.05 + i * 0.2));
      const run = 4 + Math.floor(rand() * 5);
      for (let k = 0; k < run; k++) onBody(x++, y, glow);
      for (let k = 0; k < 2; k++) onBody(x, y++, glow);
      for (let k = 0; k < 3; k++) onBody(x++, y, glow);
    }
  }
  if (theme.feature === "stripes") {
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++) if ((x + y) % 7 < 2 && y > cy - R * 0.3) onBody(x, y, light);
  }
  if (theme.feature === "fins") {
    for (let i = 0; i < 4; i++) {
      const bx = Math.round(cx - R * 0.5 + rand() * R);
      const by = Math.round(cy + R * 0.3 + rand() * R * 0.4);
      onBody(bx, by, C.coat);
      onBody(bx + 1, by, C.coatShade);
    }
  }

  // eyes: one to three, aliens get three to five - glancing left, at the player
  const eyeCount = tentacled ? 3 + Math.floor(rand() * 3) : 1 + Math.floor(rand() * 3);
  const s = eyeCount === 1 ? (R > 12 ? 7 : 6) : eyeCount === 2 ? 4 : 3;
  const spread = R * 1.0;
  const eyeY = Math.round(cy - R * 0.2);
  const eyes: EnemySprite["eyes"] = [];
  const pupil = theme.glow ? (tentacled ? C.greenHi : C.cyan) : C.ink;
  for (let i = 0; i < eyeCount; i++) {
    const ex = Math.round((eyeCount === 1 ? cx : cx - spread / 2 + (i * spread) / (eyeCount - 1)) - s / 2);
    const ey = eyeY - Math.round(s / 2) + (eyeCount > 2 && i % 2 ? -2 : 0);
    for (let y = -1; y <= s; y++) for (let x = -1; x <= s; x++) set(ex + x, ey + y, C.ink);
    for (let y = 0; y < s; y++)
      for (let x = 0; x < s; x++) {
        const corner = s > 3 && (x === 0 || x === s - 1) && (y === 0 || y === s - 1);
        set(ex + x, ey + y, corner ? C.ink : y === s - 1 ? C.coat : C.white);
      }
    const p = Math.max(1, Math.floor(s / 2.5));
    for (let y = 0; y < p; y++) for (let x = 0; x < p; x++) set(ex + 1 + x, ey + Math.floor((s - p) / 2) + y, pupil);
    if (pupil !== C.ink) set(ex + 1, ey + Math.floor((s - p) / 2), C.ink);
    eyes.push({ x: ex, y: ey, s });
  }
  // angry brows when it hits hard
  if (atkT >= 0.4) {
    const left = eyes[0];
    const right = eyes[eyes.length - 1];
    for (let k = 0; k < 3; k++) {
      set(left.x - 1 + k, left.y - 3 + k, C.ink);
      set(right.x + right.s - k, right.y - 3 + k, C.ink);
    }
  }

  // mouth and teeth
  const mouthW = Math.round(R * 0.9);
  const mouthY = Math.round(cy + R * 0.38);
  const mx = Math.round(cx - mouthW / 2);
  const depth = 2 + Math.round(atkT * 2);
  for (let x = 0; x < mouthW; x++) {
    const t = x / (mouthW - 1);
    const d = Math.round(Math.sin(t * Math.PI) * depth);
    for (let y = 0; y <= d; y++) set(mx + x, mouthY + y, y === d ? C.ink : C.redDark);
    set(mx + x, mouthY, C.ink);
  }
  const teeth = 2 + Math.round(atkT * 4);
  for (let i = 0; i < teeth; i++) {
    const tx = mx + 1 + Math.round(((i + 0.5) * (mouthW - 2)) / teeth);
    set(tx, mouthY + 1, C.white);
    if (atkT > 0.5) set(tx, mouthY + 2, C.coat);
  }

  // 1px ink outline around the whole silhouette
  const outline: number[] = [];
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++)
      if (!get(x, y) && (get(x - 1, y) || get(x + 1, y) || get(x, y - 1) || get(x, y + 1))) outline.push(y * W + x);
  for (const i of outline) px[i] = C.ink + 1;

  let top = 0;
  while (top < H && !px.subarray(top * W, top * W + W).some(Boolean)) top++;

  return { w: W, h: H, pixels: px, eyes, top, ramp: ATTACK_RAMP[theme.feature], body };
}
