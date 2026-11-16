import {
  ATTACK_RANGE,
  HP_RANGE,
  clamp01,
  hashString,
  mulberry32,
  themeFor,
  type BodyShape,
  type Feature,
  type Theme,
} from "../components/enemyShape";
import { finalBossSprite } from "./finalBoss";
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
  // what the body looks like: the shape and its standout feature. Absent for
  // the old enemies, which then draw from the name and the setting as before.
  bodyShape?: BodyShape;
  feature?: Feature;
  // the run's final boss - hand-drawn, see finalBoss.ts
  finalBoss?: boolean;
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

// the filled body silhouette as a 64*64 grid: 1 = the pixel is inside the
// body, 0 = outside. Shading, the rift's edge color and the theme markings
// test on this grid, so they only ever touch pixels the body covers.
type Mask = Uint8Array;

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
  if (spec.finalBoss) return finalBossSprite();
  const key = `${spec.name}|${spec.maxHp}|${spec.attack}|${spec.setting}|${spec.bodyShape ?? ""}|${spec.feature ?? ""}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const sprite = build(spec);
  cache.set(key, sprite);
  return sprite;
}

function build(spec: EnemySpec): EnemySprite {
  const { name, maxHp, attack, setting } = spec;
  const theme = themeFor(setting);
  // the spec's own feature wins over the setting's theme feature
  const feature = spec.feature ?? theme.feature;
  const rand = mulberry32(hashString(name));
  const hpT = clamp01((maxHp - HP_RANGE[0]) / (HP_RANGE[1] - HP_RANGE[0]));
  const atkT = clamp01((attack - ATTACK_RANGE[0]) / (ATTACK_RANGE[1] - ATTACK_RANGE[0]));
  const rampBase = C.enemyRamps + FEATURES.indexOf(feature) * 6 + (rand() < 0.5 ? 0 : 3);
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
  const tentacled = feature === "tentacles";
  let cy = H - 1 - R * 0.92 - (tentacled ? 7 : 0);
  const eyes: EnemySprite["eyes"] = [];

  // the body, picked by shape; blob (and enemies that predate the field)
  // draw today's radial body, verbatim - same order, same rand() sequence
  let mask: Mask;
  // every other shape sets its own eyes, mouth and spikes, because the blob's
  // cy anchor and its tentacled eye logic belong to the blob body alone.
  // build() runs this after the theme markings, so they land on top of them
  // the way the blob's eyes and mouth do.
  let decorate: ((eyes: EnemySprite["eyes"]) => void) | null = null;
  switch (spec.bodyShape) {
    case "swarm": {
      const shape = swarmBody(R, rand, cx, dark, mid, light, atkT, feature, shapePupil(theme), set);
      mask = shape.mask;
      cy = shape.cy;
      decorate = shape.decorate;
      break;
    }
    case "brute": {
      const shape = bruteBody(R, rand, cx, dark, mid, light, atkT, feature, shapePupil(theme), set);
      mask = shape.mask;
      cy = shape.cy;
      decorate = shape.decorate;
      break;
    }
    case "machine": {
      const shape = machineBody(R, rand, cx, dark, mid, light, atkT, feature, shapePupil(theme), set);
      mask = shape.mask;
      cy = shape.cy;
      decorate = shape.decorate;
      break;
    }
    case "ghost": {
      const shape = ghostBody(R, rand, cx, dark, mid, light, atkT, feature, shapePupil(theme), set);
      mask = shape.mask;
      cy = shape.cy;
      decorate = shape.decorate;
      break;
    }
    case "serpent": {
      const shape = serpentBody(R, rand, dark, mid, light, atkT, feature, shapePupil(theme), set);
      mask = shape.mask;
      cy = shape.cy;
      decorate = shape.decorate;
      break;
    }
    default:
      mask = blobBody(R, rand, cx, cy, feature, atkT, dark, mid, light, set);
  }

  // theme markings, clipped to the body
  const onBody = (x: number, y: number, c: number) => {
    if (x >= 0 && y >= 0 && x < W && y < H && mask[y * W + x] === 1) set(x, y, c);
  };
  if (feature === "circuits") {
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
  if (feature === "stripes") {
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++) if ((x + y) % 7 < 2 && y > cy - R * 0.3) onBody(x, y, light);
  }
  if (feature === "fins") {
    for (let i = 0; i < 4; i++) {
      const bx = Math.round(cx - R * 0.5 + rand() * R);
      const by = Math.round(cy + R * 0.3 + rand() * R * 0.4);
      onBody(bx, by, C.coat);
      onBody(bx + 1, by, C.coatShade);
    }
  }

  if (decorate) {
    // the new shapes put their eyes, mouth and spikes on their own body
    decorate(eyes);
  } else {
    // blob eyes: one to three, aliens get three to five - glancing left, at
    // the player
    const eyeCount = tentacled ? 3 + Math.floor(rand() * 3) : 1 + Math.floor(rand() * 3);
    const s = eyeCount === 1 ? (R > 12 ? 7 : 6) : eyeCount === 2 ? 4 : 3;
    const spread = R * 1.0;
    const eyeY = Math.round(cy - R * 0.2);
    const pupil = theme.glow ? (tentacled ? C.greenHi : C.cyan) : C.ink;
    for (let i = 0; i < eyeCount; i++) {
      const ex = Math.round((eyeCount === 1 ? cx : cx - spread / 2 + (i * spread) / (eyeCount - 1)) - s / 2);
      const ey = eyeY - Math.round(s / 2) + (eyeCount > 2 && i % 2 ? -2 : 0);
      paintEye(ex, ey, s, pupil, set);
      eyes.push({ x: ex, y: ey, s });
    }
  }
  // angry brows when it hits hard, on the outermost eyes of any body
  if (atkT >= 0.4 && eyes.length > 0) {
    const left = eyes[0];
    const right = eyes[eyes.length - 1];
    for (let k = 0; k < 3; k++) {
      set(left.x - 1 + k, left.y - 3 + k, C.ink);
      set(right.x + right.s - k, right.y - 3 + k, C.ink);
    }
  }

  // mouth and teeth: only the blob gets the wide one centered on its cy, the
  // other shapes paint a mouth that fits their body in their decorate step
  if (!decorate) {
    const mouthW = Math.round(R * 0.9);
    const mouthY = Math.round(cy + R * 0.38);
    paintMouth(cx, mouthY, mouthW, 2 + Math.round(atkT * 2), atkT, set);
  }

  // 1px ink outline around the silhouette. The blob keeps the step exactly as it
  // always was - the pinned values in scripts/legacy-sprite-reference.mjs lock
  // those pixels. The other shapes outline only the empty pixels the background
  // reaches from the canvas edge (a flood fill over 4-neighbours): the holes in
  // a ghost's lower third are not reachable that way, so they stay see-through
  // instead of filling in as black specks.
  const outline: number[] = [];
  if (decorate) {
    const outside = new Uint8Array(W * H);
    const seen: number[] = [];
    const reachable = (i: number) => {
      if (!px[i] && !outside[i]) {
        outside[i] = 1;
        seen.push(i);
      }
    };
    for (let x = 0; x < W; x++) {
      reachable(x);
      reachable((H - 1) * W + x);
    }
    for (let y = 1; y < H - 1; y++) {
      reachable(y * W);
      reachable(y * W + W - 1);
    }
    for (let n = 0; n < seen.length; n++) {
      const i = seen[n];
      const x = i % W;
      const y = (i - x) / W;
      if (get(x - 1, y) || get(x + 1, y) || get(x, y - 1) || get(x, y + 1)) outline.push(i);
      if (x > 0) reachable(i - 1);
      if (x < W - 1) reachable(i + 1);
      if (y > 0) reachable(i - W);
      if (y < H - 1) reachable(i + W);
    }
  } else {
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++)
        if (!get(x, y) && (get(x - 1, y) || get(x + 1, y) || get(x, y - 1) || get(x, y + 1))) outline.push(y * W + x);
  }
  for (const i of outline) px[i] = C.ink + 1;

  let top = 0;
  while (top < H && !px.subarray(top * W, top * W + W).some(Boolean)) top++;

  return { w: W, h: H, pixels: px, eyes, top, ramp: ATTACK_RAMP[feature], body };
}

// the blob body: a bumpy radial silhouette, the shape the enemies drew before
// the bodyShape field existed. Draws everything of it that has always been
// drawn in this order - silhouette points, spikes along the top, the horns,
// tentacles and fins of the setting's feature, the lit body fill, the rift's
// cyan edge, the glint - and returns the filled silhouette as a Mask, which
// the steps after it in build() clip the theme markings to.
//
// The decorations run before the body fill on purpose: the fill paints over
// the parts of horns, tentacles and fins that reach into the body, and the
// glint paints over the rest of what it covers. Moving them after the fill
// would change the pixels, so they stay where they always were.
function blobBody(
  R: number,
  rand: () => number,
  cx: number,
  cy: number,
  feature: Feature,
  atkT: number,
  dark: number,
  mid: number,
  light: number,
  set: (x: number, y: number, c: number) => void,
): Mask {
  const W = SIZE;
  const H = SIZE;

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

  // the silhouette as a grid: 1 wherever inBody holds, the same test the
  // per-pixel loops below run, so they can read this instead
  const mask = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (inBody(x, y)) mask[y * W + x] = 1;
  const inMask = (x: number, y: number) => x >= 0 && y >= 0 && x < W && y < H && mask[y * W + x] === 1;

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

  // horns, tentacles and fins of the setting's feature, moved into helpers the
  // other shapes can anchor on their own head or body edge. The blob passes its
  // own cx, cy and R with scale 1, which draws exactly what it drew before -
  // including the tentacles' rand() calls at this point in the sequence.
  if (feature === "horns") drawHorns(cx, cy, R, 1, set);
  if (feature === "tentacles") drawTentacles(cx, cy + R * 0.5, R * 0.6, R * 1.2, 6, dark, mid, rand, set);
  if (feature === "fins") drawFins(cx, cy, R * 0.85, 1, light, set);

  // the body, lit from the upper left, with the rift's cyan on its left edge
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (!inMask(x, y)) continue;
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
      if (!inMask(x, y) || inMask(x - 1, y)) continue;
      const ny = (y + 0.5 - cy) / R;
      if (ny > -0.7 && ny < 0.6) set(x, y, ny < 0.1 ? C.cyanHi : C.cyan);
    }
  }
  // specular glint
  set(Math.round(cx - R * 0.4), Math.round(cy - R * 0.55), C.white);
  set(Math.round(cx - R * 0.4) + 1, Math.round(cy - R * 0.55), light);

  return mask;
}

// shared types for the non-blob body shapes
type SetPixel = (x: number, y: number, c: number) => void;
type BodyResult = {
  mask: Mask;
  // the vertical anchor the theme markings in build() read off
  cy: number;
  // paints this body's own eyes, mouth and (for machine) spikes, and pushes
  // its eye boxes into eyes; build() runs it after the theme markings, the way
  // the blob's eyes and mouth follow its body
  decorate: (eyes: EnemySprite["eyes"]) => void;
};

// the blob always painted an eye like this; the new shapes reuse it so every
// body's eyes are drawn the same way (ink frame, white, a glinting pupil)
function paintEye(ex: number, ey: number, s: number, pupil: number, set: SetPixel) {
  for (let y = -1; y <= s; y++) for (let x = -1; x <= s; x++) set(ex + x, ey + y, C.ink);
  for (let y = 0; y < s; y++)
    for (let x = 0; x < s; x++) {
      const corner = s > 3 && (x === 0 || x === s - 1) && (y === 0 || y === s - 1);
      set(ex + x, ey + y, corner ? C.ink : y === s - 1 ? C.coat : C.white);
    }
  const p = Math.max(1, Math.floor(s / 2.5));
  for (let y = 0; y < p; y++) for (let x = 0; x < p; x++) set(ex + 1 + x, ey + Math.floor((s - p) / 2) + y, pupil);
  if (pupil !== C.ink) set(ex + 1, ey + Math.floor((s - p) / 2), C.ink);
}

// the open mouth with teeth, depth and tooth count from atkT - the same pixels
// the blob always drew, so the mouth scales with attack on every shape
function paintMouth(cx: number, mouthY: number, mouthW: number, depth: number, atkT: number, set: SetPixel) {
  const mx = Math.round(cx - mouthW / 2);
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
}

// the pupil for the new shapes: the blob's cyan-when-glowing eye color minus
// the tentacled branch, which only ever applied to the blob body
function shapePupil(theme: Theme): number {
  return theme.glow ? C.cyan : C.ink;
}

// shade one body pixel lit from the upper left, the way the blob shades itself
function litColor(lit: number, dark: number, mid: number, light: number): number {
  return lit > 0.35 ? light : lit > -0.35 ? mid : dark;
}

// the feature decorations, split out of blobBody so every shape can put them on
// its own head, its own bottom edge or its own side edge. blobBody passes its
// own anchor and scale 1, which reproduces its original pixels exactly.

// horns: two bone-colored crescents. (cx, cy, R) is the anchor the blob used,
// k scales the crescent itself for the shapes with a smaller head.
function drawHorns(cx: number, cy: number, R: number, k: number, set: SetPixel) {
  for (const side of [-1, 1]) {
    const bx = cx + side * R * 0.45;
    const by = cy - R * 0.6;
    for (let t = 0; t <= 1; t += 0.02) {
      const hx = bx + side * (Math.sin(t * 1.4) * 9) * k;
      const hy = by - t * 10 * k + t * t * 2 * k;
      const thick = Math.max(1, Math.round((1 - t) * 2.5 * k));
      for (let d = 0; d < thick; d++) set(Math.round(hx) + (side > 0 ? -d : d), Math.round(hy), t > 0.7 ? C.coat : C.brassHi);
    }
  }
}

// tentacles hanging down from startY to the canvas floor. half/span bound where
// they start across the body, sway how far they swing out.
function drawTentacles(
  cx: number,
  startY: number,
  half: number,
  span: number,
  sway: number,
  dark: number,
  mid: number,
  rand: () => number,
  set: SetPixel,
  // how far down the tentacles reach; the default runs them to the floor
  maxLen: number = SIZE,
) {
  const yStart = Math.round(startY);
  // a floating body (the swarm) passes a short length, so its tentacles hang
  // below it instead of standing as a pillar down to the floor
  const H = Math.min(SIZE, yStart + Math.max(2, Math.round(maxLen)));
  const count = 3 + Math.floor(rand() * 3);
  for (let i = 0; i < count; i++) {
    const x0 = cx - half + (i * span) / (count - 1);
    const swing = (rand() - 0.5) * sway;
    for (let y = yStart; y < H; y++) {
      const t = (y - startY) / (H - startY);
      const x = Math.round(x0 + Math.sin(t * Math.PI) * swing);
      set(x, y, dark);
      set(x + 1, y, t < 0.7 ? mid : dark);
    }
  }
}

// fins at the sides: a triangle out of the body edge. out is how far the fin's
// root sits from cx, k scales its size.
function drawFins(cx: number, cy: number, out: number, k: number, light: number, set: SetPixel) {
  const W = SIZE;
  const H = SIZE;
  for (const side of [-1, 1]) {
    const bx = cx + side * out;
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++)
        if (inTriangle(x + 0.5, y + 0.5, bx, cy - 2 * k, bx + side * 8 * k, cy - 5 * k, bx + side * 3 * k, cy + 6 * k)) set(x, y, light);
  }
}

// the attack spikes, standing on the top edge of a shape's mask: same count and
// length as the blob's (more and longer the harder it hits), placed on the body
// columns that mask covers instead of on the blob's radius.
function topEdgeSpikes(mask: Mask, atkT: number, dark: number, mid: number, set: SetPixel) {
  const W = SIZE;
  const H = SIZE;
  // the topmost mask row of every body column
  const topAt = new Int16Array(W).fill(-1);
  const cols: number[] = [];
  for (let x = 0; x < W; x++) {
    for (let y = 0; y < H; y++)
      if (mask[y * W + x]) {
        topAt[x] = y;
        cols.push(x);
        break;
      }
  }
  if (!cols.length) return;
  const spikeCount = 2 + Math.round(atkT * 5);
  const spikeLength = 3 + Math.round(atkT * 6);
  for (let i = 0; i < spikeCount; i++) {
    const x = cols[Math.round((i * (cols.length - 1)) / (spikeCount - 1))];
    for (let k = 1; k <= spikeLength; k++) {
      const half = Math.max(0, Math.round((1 - k / spikeLength) * 1.5));
      const y = topAt[x] - k;
      for (let dx = -half; dx <= half; dx++) set(x + dx, y, (x + dx + y) % 5 === 0 ? mid : dark);
    }
  }
}

// swarm: 5-7 small bodies, each with its own pair of eyes. Centers are spread
// over the canvas on a loose 4-wide grid so none of them is clamped away. The
// feature decoration goes on the body closest to the center.
function swarmBody(
  R: number,
  rand: () => number,
  cx: number,
  dark: number,
  mid: number,
  light: number,
  atkT: number,
  feature: Feature,
  pupil: number,
  set: SetPixel,
): BodyResult {
  const W = SIZE;
  const H = SIZE;
  const mask = new Uint8Array(W * H);
  const r = Math.max(2, Math.round(R / 3));
  const count = 5 + Math.floor(rand() * 3);
  const centers: { x: number; y: number }[] = [];
  for (let i = 0; i < count; i++) {
    const col = i % 4;
    const row = Math.floor(i / 4);
    const x = Math.max(
      r + 1,
      Math.min(W - 2 - r, Math.round((W / 4) * (col + 0.5) + (rand() - 0.5) * (W / 4) * 0.5)),
    );
    const y = Math.max(
      r + 1,
      Math.min(H - 2 - r, Math.round((H / 2.4) * (row + 0.5) + (rand() - 0.5) * (H / 2.4) * 0.5) + 3),
    );
    centers.push({ x, y });
  }
  for (const c of centers) {
    for (let y = c.y - r; y <= c.y + r; y++)
      for (let x = c.x - r; x <= c.x + r; x++) {
        const dx = x + 0.5 - c.x;
        const dy = y + 0.5 - c.y;
        if (dx * dx + dy * dy > r * r) continue;
        mask[y * W + x] = 1;
        set(x, y, litColor(-(dx / r) * 0.55 - (dy / r) * 0.8, dark, mid, light));
      }
  }
  const cy = Math.round(centers.reduce((sum, c) => sum + c.y, 0) / centers.length);
  const s = r >= 4 ? 2 : 1;
  // the body closest to the canvas center gets the mouth; the rest are eyes only
  let central = centers[0];
  let best = Infinity;
  for (const c of centers) {
    const d = (c.x - cx) * (c.x - cx) + (c.y - cy) * (c.y - cy);
    if (d < best) {
      best = d;
      central = c;
    }
  }
  // the feature on the central body, then the attack spikes on the bodies' tops
  if (feature === "horns") drawHorns(central.x, central.y - r * 0.4, r * 1.6, r / 6, set);
  if (feature === "tentacles") drawTentacles(central.x, central.y + r * 0.5, r * 0.6, r * 1.2, 4, dark, mid, rand, set, r * 2);
  if (feature === "fins") drawFins(central.x, central.y, r * 0.9, Math.max(1, r / 6), light, set);
  const decorate = (eyes: EnemySprite["eyes"]) => {
    topEdgeSpikes(mask, atkT, dark, mid, set);
    for (const c of centers) {
      const ey = c.y - Math.round(s / 2);
      const lx = c.x - s - 1;
      const rx = c.x + 1;
      paintEye(lx, ey, s, pupil, set);
      paintEye(rx, ey, s, pupil, set);
      eyes.push({ x: lx, y: ey, s }, { x: rx, y: ey, s });
    }
    const mw = Math.max(2, Math.round(r * 1.4));
    paintMouth(central.x, central.y + r - 1, mw, 1 + Math.round(atkT * 2), atkT, set);
  };
  return { mask, cy, decorate };
}

// brute: a wide ellipse body (width ~1.6R) with a small head circle (~R/3) on
// top, sitting on the floor like the blob. The eyes sit in the head, the mouth
// just under it. The body itself is fixed, only its size scales with R; rand is
// for the tentacles of the feature.
function bruteBody(
  R: number,
  rand: () => number,
  cx: number,
  dark: number,
  mid: number,
  light: number,
  atkT: number,
  feature: Feature,
  pupil: number,
  set: SetPixel,
): BodyResult {
  const W = SIZE;
  const H = SIZE;
  const mask = new Uint8Array(W * H);
  const hr = Math.max(3, Math.round(R / 3));
  const w = Math.min(cx - 2, Math.round(0.8 * R));
  const h = Math.max(4, Math.round(0.5 * R));
  // the body sits on the arena floor like the blob's, head on top of it
  const by = H - 2 - h;
  const hy = Math.max(hr + 1, by - h - Math.round(hr * 0.3));
  // head disc
  for (let y = hy - hr; y <= hy + hr; y++)
    for (let x = cx - hr; x <= cx + hr; x++) {
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - hy;
      if (dx * dx + dy * dy > hr * hr) continue;
      mask[y * W + x] = 1;
      set(x, y, litColor(-(dx / hr) * 0.55 - (dy / hr) * 0.8, dark, mid, light));
    }
  // body ellipse
  for (let y = by - h; y <= by + h; y++)
    for (let x = cx - w; x <= cx + w; x++) {
      const dx = (x + 0.5 - cx) / w;
      const dy = (y + 0.5 - by) / h;
      if (dx * dx + dy * dy > 1) continue;
      mask[y * W + x] = 1;
      set(x, y, litColor(-dx * 0.55 - dy * 0.8, dark, mid, light));
    }
  const cy = by;
  const s = hr >= 5 ? 3 : 2;
  // horns on the head, tentacles under the body, fins at its sides
  if (feature === "horns") drawHorns(cx, hy, hr * 1.6, hr / 6, set);
  if (feature === "tentacles") drawTentacles(cx, by + h * 0.4, w * 0.6, w * 1.2, 4, dark, mid, rand, set);
  if (feature === "fins") drawFins(cx, by, w * 0.9, Math.max(1, h / 6), light, set);
  const decorate = (eyes: EnemySprite["eyes"]) => {
    topEdgeSpikes(mask, atkT, dark, mid, set);
    const ey = hy - Math.round(s / 2);
    const lx = cx - s - 1;
    const rx = cx + 1;
    paintEye(lx, ey, s, pupil, set);
    paintEye(rx, ey, s, pupil, set);
    eyes.push({ x: lx, y: ey, s }, { x: rx, y: ey, s });
    const mw = Math.max(2, Math.round(hr * 1.6));
    paintMouth(cx, hy + hr, mw, 2 + Math.round(atkT * 2), atkT, set);
  };
  return { mask, cy, decorate };
}

// machine: only rectangles with straight edges - a torso plus 1-2 side
// attachments picked with rand. No rounded corners, no edge noise. Spikes meet
// the straight top edge head-on, more of them the harder it hits.
function machineBody(
  R: number,
  rand: () => number,
  cx: number,
  dark: number,
  mid: number,
  light: number,
  atkT: number,
  feature: Feature,
  pupil: number,
  set: SetPixel,
): BodyResult {
  const W = SIZE;
  const H = SIZE;
  const mask = new Uint8Array(W * H);
  const tw = Math.max(3, Math.min(cx - 6, Math.round(0.7 * R)));
  const th = Math.max(6, Math.round(1.1 * R));
  // the torso stands on the arena floor like the blob's
  const y1 = H - 2;
  const cyT = y1 - Math.round(th / 2);
  const x0 = cx - tw;
  const x1 = cx + tw;
  const y0 = Math.max(1, cyT - Math.round(th / 2));
  const rect = (xa: number, ya: number, xb: number, yb: number) => {
    const l = Math.max(0, xa);
    const rt = Math.min(W - 1, xb);
    const t = Math.max(0, ya);
    const b = Math.min(H - 1, yb);
    for (let y = t; y <= b; y++)
      for (let x = l; x <= rt; x++) {
        mask[y * W + x] = 1;
        const lit = -((x + 0.5 - cx) / tw) * 0.55 - ((y + 0.5 - cyT) / th) * 0.8;
        set(x, y, litColor(lit, dark, mid, light));
      }
  };
  rect(x0, y0, x1, y1);
  // 1-2 straight side attachments
  const parts = 1 + Math.floor(rand() * 2);
  for (let i = 0; i < parts; i++) {
    const side = rand() < 0.5 ? -1 : 1;
    const aw = 2 + Math.round(rand() * 3);
    const ah = 3 + Math.round(rand() * (th * 0.5));
    const ax = side < 0 ? x0 - aw : x1 + 1;
    const ay = Math.min(y1 - ah, Math.max(y0, Math.round(y0 + rand() * (y1 - y0 - ah))));
    rect(ax, ay, ax + aw - 1, ay + ah - 1);
  }
  const cy = cyT;
  const s = 3;
  // horns at the torso's top corners, tentacles under it, fins at its sides
  if (feature === "horns") drawHorns(cx, y0, tw * 1.6, tw / 10, set);
  if (feature === "tentacles") drawTentacles(cx, y1 - th * 0.3, tw * 0.6, tw * 1.2, 4, dark, mid, rand, set);
  if (feature === "fins") drawFins(cx, cyT, tw * 1.1, Math.max(1, th / 12), light, set);
  const decorate = (eyes: EnemySprite["eyes"]) => {
    // straight-up spikes off the mask's top edge, count and length from atkT
    topEdgeSpikes(mask, atkT, dark, mid, set);
    const ey = y0 + 2;
    const lx = cx - s - 1;
    const rx = cx + 1;
    paintEye(lx, ey, s, pupil, set);
    paintEye(rx, ey, s, pupil, set);
    eyes.push({ x: lx, y: ey, s }, { x: rx, y: ey, s });
    const mw = Math.max(2, Math.round(tw * 1.2));
    paintMouth(cx, y1 - Math.round(th * 0.25), mw, 2 + Math.round(atkT * 2), atkT, set);
  };
  return { mask, cy, decorate };
}

// ghost: a half-circle top over a rectangular body. The bottom edge is jagged
// (rand fringe) and the lower third has rand holes (~25%), so it reads half
// through the rift. It is the one shape allowed to float above the floor.
function ghostBody(
  R: number,
  rand: () => number,
  cx: number,
  dark: number,
  mid: number,
  light: number,
  atkT: number,
  feature: Feature,
  pupil: number,
  set: SetPixel,
): BodyResult {
  const W = SIZE;
  const H = SIZE;
  const mask = new Uint8Array(W * H);
  const gr = Math.max(3, Math.min(cx - 2, Math.round(0.7 * R)));
  const discY = 24;
  const bottom = 50;
  const holeTop = Math.round(bottom - (bottom - discY) / 3);
  const put = (x: number, y: number, dx: number, dy: number, scale: number) => {
    if (x < 0 || y < 0 || x >= W || y >= H) return;
    mask[y * W + x] = 1;
    set(x, y, litColor(-(dx / scale) * 0.55 - (dy / scale) * 0.8, dark, mid, light));
  };
  // half-circle top
  for (let y = discY - gr; y <= discY; y++)
    for (let x = cx - gr; x <= cx + gr; x++) {
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - discY;
      if (dx * dx + dy * dy > gr * gr) continue;
      put(x, y, dx, dy, gr);
    }
  // rectangular body with a jagged bottom and holes in the lower third
  for (let x = cx - gr; x <= cx + gr; x++) {
    const dx = x + 0.5 - cx;
    const foot = bottom - Math.floor(rand() * 4);
    for (let y = discY + 1; y <= foot; y++) {
      if (y >= holeTop && rand() < 0.25) continue;
      put(x, y, dx, y + 0.5 - discY, gr);
    }
  }
  const cy = discY + gr;
  const s = gr >= 6 ? 3 : 2;
  // horns above the dome, tentacles hanging off the fringe, fins at the flanks
  if (feature === "horns") drawHorns(cx, discY - gr * 0.6, gr * 1.2, gr / 9, set);
  if (feature === "tentacles") drawTentacles(cx, bottom - 3, gr * 0.6, gr * 1.2, 5, dark, mid, rand, set);
  if (feature === "fins") drawFins(cx, discY + gr * 0.6, gr * 0.95, gr / 9, light, set);
  const decorate = (eyes: EnemySprite["eyes"]) => {
    topEdgeSpikes(mask, atkT, dark, mid, set);
    const ey = discY - Math.round(s / 2) - 1;
    const lx = cx - s - 1;
    const rx = cx + 1;
    paintEye(lx, ey, s, pupil, set);
    paintEye(rx, ey, s, pupil, set);
    eyes.push({ x: lx, y: ey, s }, { x: rx, y: ey, s });
    const mw = Math.max(2, Math.round(gr * 0.9));
    paintMouth(cx, discY + 3, mw, 1 + Math.round(atkT * 2), atkT, set);
  };
  return { mask, cy, decorate };
}

// serpent: a sine body running across the canvas, thick at the head (left) and
// thinning to the tail (right). The head carries the eyes and the mouth. The
// curve is pushed down as far as it reaches, so the body stands on the arena
// floor like the blob's.
function serpentBody(
  R: number,
  rand: () => number,
  dark: number,
  mid: number,
  light: number,
  atkT: number,
  feature: Feature,
  pupil: number,
  set: SetPixel,
): BodyResult {
  const W = SIZE;
  const H = SIZE;
  const mask = new Uint8Array(W * H);
  const x0 = 8;
  const x1 = 57;
  const amp = Math.min(7, Math.round(0.35 * R));
  const phase = rand() * Math.PI * 2;
  const waves = 1 + Math.floor(rand() * 2);
  const wl = (x1 - x0) / waves;
  const headT = Math.max(4, Math.round(0.6 * R));
  const tailT = 2;
  const thickAt = (x: number) => Math.max(tailT, Math.round(headT - ((headT - tailT) * (x - x0)) / (x1 - x0)));
  const waveAt = (x: number) => amp * Math.sin(((x - x0) / wl) * Math.PI * 2 + phase);
  let lowest = 0;
  for (let x = x0; x <= x1; x++) lowest = Math.max(lowest, waveAt(x) + thickAt(x));
  const midY = H - 2 - Math.round(lowest);
  const yAt = (x: number) => midY + waveAt(x);
  for (let x = x0; x <= x1; x++) {
    const th = thickAt(x);
    const c = yAt(x);
    for (let y = Math.round(c - th); y <= Math.round(c + th); y++) {
      if (y < 1 || y > H - 2) continue;
      const dy = (y + 0.5 - c) / th;
      mask[y * W + x] = 1;
      set(x, y, litColor(-dy * 0.8 - 0.05, dark, mid, light));
    }
  }
  const cy = midY;
  const headX = x0 + Math.round(headT * 0.5);
  const headY = Math.round(yAt(headX));
  const s = headT >= 6 ? 3 : 2;
  const midX = Math.round((x0 + x1) / 2);
  // horns on the head, tentacles under the body's middle, fins along its sides
  if (feature === "horns") drawHorns(headX, headY - headT * 0.4, headT * 1.6, headT / 9, set);
  if (feature === "tentacles") drawTentacles(midX, yAt(midX) + thickAt(midX) * 0.5, 6, 12, 4, dark, mid, rand, set);
  if (feature === "fins") drawFins(midX, midY, headT * 1.4, Math.max(1, headT / 8), light, set);
  const decorate = (eyes: EnemySprite["eyes"]) => {
    topEdgeSpikes(mask, atkT, dark, mid, set);
    const ey = headY - Math.round(s / 2) - 1;
    const lx = headX - s - 1;
    const rx = headX + 1;
    paintEye(lx, ey, s, pupil, set);
    paintEye(rx, ey, s, pupil, set);
    eyes.push({ x: lx, y: ey, s }, { x: rx, y: ey, s });
    const mw = Math.max(2, Math.round(headT * 1.1));
    paintMouth(headX, headY + Math.round(s * 0.5) + 1, mw, 1 + Math.round(atkT * 2), atkT, set);
  };
  return { mask, cy, decorate };
}
