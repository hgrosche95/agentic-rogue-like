// The machine world's backdrop behind the enemy: one per preset setting,
// built from plain pixel shapes in the fixed palette. The scene paints it
// once into its background buffer (scene.ts paintBackground), never per frame.
// A setting the player typed themselves gets one of the five by its name's hash.

import { hashString } from "../components/enemyShape";
import { C } from "./palette";
import { FLOOR, RIFT_X, WIDTH } from "./layout";

export type Backdrop = "dungeon" | "cyberpunk" | "alien" | "pirate" | "carnival";

const PRESETS: Record<string, Backdrop> = {
  dungeon: "dungeon",
  cyberpunk: "cyberpunk",
  "alien planet": "alien",
  "pirate seas": "pirate",
  "haunted carnival": "carnival",
};

const ALL: Backdrop[] = ["dungeon", "cyberpunk", "alien", "pirate", "carnival"];

export function backdropFor(setting: string): Backdrop {
  const key = setting.trim().toLowerCase();
  return PRESETS[key] ?? ALL[hashString(key) % ALL.length];
}

// rect / dithered rect into the background buffer (scene.ts)
type Paint = (x: number, y: number, w: number, h: number, c: number) => void;

function hash(n: number): number {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
}

// the right half, from just past the rift to the edge, above the floor
const X = RIFT_X + 1;
const W = WIDTH - X;

// the torches on the dungeon's pillars - their flames flicker (scene.ts)
export const TORCHES: readonly [number, number][] = [
  [146, 50],
  [182, 50],
  [218, 50],
];

// the cyberpunk racks - their LEDs blink (scene.ts)
export const RACKS = 7;
export const rackX = (i: number) => 126 + i * 16;
export const rackHeight = (i: number) => 22 + Math.round(hash(i * 5 + 3) * 16);

// the backdrops with an open sky get the scene's twinkling stars
export const hasSky = (b: Backdrop) => b !== "dungeon";

export function paintBackdrop(kind: Backdrop, r: Paint, d: Paint) {
  switch (kind) {
    case "dungeon":
      return dungeon(r, d);
    case "alien":
      return alien(r, d);
    case "pirate":
      return pirate(r, d);
    case "carnival":
      return carnival(r, d);
    default:
      return cyberpunk(r, d);
  }
}

// a night sky fading from deep night at the top to violet at the horizon
function sky(r: Paint, d: Paint, horizon: number = C.violet) {
  r(X, 0, W, FLOOR, C.deepNight);
  d(X, 18, W, 6, C.night);
  r(X, 24, W, 30, C.night);
  d(X, 54, W, 6, horizon);
  r(X, 60, W, FLOOR - 60, horizon);
}

// a filled disc
function disc(r: Paint, cx: number, cy: number, rad: number, c: number) {
  for (let y = -rad; y <= rad; y++) {
    const half = Math.floor(Math.sqrt(rad * rad - y * y));
    r(cx - half, cy + y, half * 2 + 1, 1, c);
  }
}

// ---------------------------------------------------------------- dungeon
// a vault: a brick wall with three pillars carrying arches, a torch on each
function dungeon(r: Paint, d: Paint) {
  r(X, 0, W, FLOOR, C.cloth0);
  // bricks: rows of 4px, staggered every other row
  for (let y = 0; y < FLOOR; y += 4) {
    const shift = (y / 4) % 2 ? 4 : 0;
    r(X, y + 3, W, 1, C.ink);
    for (let x = X - shift; x < WIDTH; x += 8) {
      if (x >= X) r(x, y, 1, 3, C.ink);
      const tone = hash(x * 3 + y) > 0.7 ? C.cloth2 : C.cloth1;
      r(Math.max(X, x + 1), y, Math.min(7, WIDTH - x - 1), 1, tone);
    }
  }
  // the dark of the arches between the pillars
  for (const [cx, w] of [
    [164, 28],
    [200, 28],
  ] as const) {
    const top = 30;
    for (let y = 0; y < w / 2; y++) {
      const half = Math.round(Math.sqrt((w / 2) ** 2 - (w / 2 - y) ** 2));
      r(cx - half, top + y, half * 2, 1, C.ink);
    }
    r(cx - w / 2, top + w / 2, w, FLOOR - top - w / 2, C.ink);
    d(cx - w / 2 + 2, top + w / 2, w - 4, FLOOR - top - w / 2, C.deepNight);
  }
  // pillars
  for (const [tx] of TORCHES) {
    const x = tx - 4;
    r(x - 1, 0, 10, FLOOR, C.ink);
    r(x, 0, 8, FLOOR, C.iron);
    r(x, 0, 1, FLOOR, C.steel);
    for (let y = 6; y < FLOOR; y += 10) r(x, y, 8, 1, C.ink);
    r(x - 2, FLOOR - 4, 12, 4, C.ink);
    r(x - 1, FLOOR - 3, 10, 3, C.steel);
  }
  // torch brackets (the flames are drawn by the scene, they flicker)
  for (const [tx, ty] of TORCHES) {
    r(tx - 2, ty, 5, 2, C.ink);
    r(tx - 1, ty, 3, 1, C.brass);
    r(tx, ty + 2, 1, 4, C.wood2);
  }
  // warm light the torches throw on the wall
  for (const [tx, ty] of TORCHES) d(tx - 8, ty - 10, 17, 8, C.amberDark);
}

// -------------------------------------------------------------- cyberpunk
// the skyline: far towers with lit windows and server racks in front
function cyberpunk(r: Paint, d: Paint) {
  sky(r, d);
  d(X, FLOOR - 8, W, 8, C.violetLight);
  for (let x = X + 2; x < WIDTH; x += 9) {
    const h = 18 + Math.round(hash(x) * 30);
    r(x, FLOOR - h, 6, h, C.deepNight);
    for (let w = 0; w < 4; w++) r(x + 1 + (w % 2) * 3, FLOOR - h + 3 + w * 5, 1, 1, C.cyanDark);
  }
  for (let i = 0; i < RACKS; i++) {
    const x = rackX(i);
    const h = rackHeight(i);
    const top = FLOOR - h;
    r(x - 1, top - 1, 10, h + 1, C.ink);
    r(x, top, 8, h, C.cloth0);
    r(x, top, 8, 1, C.violetLight);
    r(x + 7, top + 1, 1, h - 1, C.night);
    r(x + 2, top + 4, 1, h - 6, C.cyanMid);
    r(x + 5, top + 4, 1, h - 6, C.cyanDark);
  }
}

// ----------------------------------------------------------- alien planet
// a magenta dusk, two moons and needles of rock
function alien(r: Paint, d: Paint) {
  sky(r, d, C.magentaDark);
  d(X, 44, W, 10, C.magentaDark);
  // the big moon, ringed, and a small one
  disc(r, 214, 15, 9, C.ink);
  disc(r, 214, 15, 8, C.greenDark);
  disc(r, 212, 13, 6, C.green);
  r(208, 10, 3, 2, C.greenHi);
  d(209, 16, 8, 4, C.greenDark);
  r(198, 16, 32, 1, C.ink);
  r(199, 15, 30, 1, C.amberHi);
  disc(r, 176, 9, 4, C.ink);
  disc(r, 176, 9, 3, C.amberDark);
  r(175, 7, 2, 1, C.amber);
  // rock needles: far row in violet, near row in ink with a lit edge
  for (const [near, step, base] of [
    [false, 7, 20],
    [true, 13, 34],
  ] as const) {
    for (let x = X + (near ? 3 : 0); x < WIDTH; x += step) {
      const h = base + Math.round(hash(x * (near ? 5 : 3)) * (near ? 26 : 18));
      const w = near ? 6 : 4;
      for (let y = 0; y < h; y++) {
        const half = Math.max(0, Math.round(((y + 1) / h) * (w / 2)));
        r(x - half, FLOOR - h + y, half * 2 + 1, 1, near ? C.ink : C.violet);
        if (near && half > 0) r(x - half, FLOOR - h + y, 1, 1, C.magentaDark);
      }
    }
  }
}

// ------------------------------------------------------------ pirate seas
// the sea under a night sky, two ships' masts against it, waves rolling in
function pirate(r: Paint, d: Paint) {
  sky(r, d, C.night);
  disc(r, 222, 12, 5, C.coat);
  r(220, 10, 2, 2, C.white);
  // the sea from the horizon down to the floor
  const sea = 58;
  r(X, sea, W, FLOOR - sea, C.cyanDark);
  r(X, sea, W, 1, C.cyanMid);
  for (let y = sea + 3, row = 0; y < FLOOR; y += 4, row++) {
    for (let x = X + ((row * 5) % 9); x < WIDTH; x += 9) {
      r(x, y, 4, 1, C.cyanMid);
      r(x + 1, y - 1, 2, 1, C.cyan);
    }
  }
  // two ships: hull on the horizon, masts with yards and furled sails
  for (const [hx, hw, masts] of [
    [166, 34, [176, 190]],
    [208, 30, [216, 229]],
  ] as const) {
    r(hx, sea - 4, hw, 5, C.ink);
    r(hx + 2, sea - 4, hw - 4, 1, C.wood2);
    for (const mx of masts) {
      const top = sea - 34 + Math.round(hash(mx) * 6);
      r(mx, top, 2, sea - 4 - top, C.wood0);
      r(mx, top, 1, sea - 4 - top, C.wood2);
      for (const [y, w] of [
        [top + 6, 14],
        [top + 18, 18],
      ] as const) {
        r(mx - w / 2 + 1, y, w, 1, C.wood1);
        r(mx - w / 2 + 2, y + 1, w - 2, 7, C.coatShade);
        d(mx - w / 2 + 2, y + 6, w - 2, 2, C.cloth2);
      }
      r(mx, top - 4, 1, 4, C.wood0);
      r(mx + 1, top - 4, 4, 2, C.red);
    }
  }
}

// ------------------------------------------------------- haunted carnival
// a striped big top and a Ferris wheel against a sickly sky
function carnival(r: Paint, d: Paint) {
  sky(r, d, C.magentaDark);
  // the Ferris wheel: rim, spokes, gondolas, legs
  const cx = 208;
  const cy = 40;
  const rad = 24;
  r(cx - 14, cy, 2, FLOOR - cy, C.ink);
  r(cx + 13, cy, 2, FLOOR - cy, C.ink);
  for (let k = 0; k < 12; k++) {
    const a = (k / 12) * Math.PI * 2;
    for (let s = 2; s < rad; s += 1) {
      r(Math.round(cx + Math.cos(a) * s), Math.round(cy + Math.sin(a) * s), 1, 1, C.cloth2);
    }
  }
  for (let k = 0; k < 160; k++) {
    const a = (k / 160) * Math.PI * 2;
    r(Math.round(cx + Math.cos(a) * rad), Math.round(cy + Math.sin(a) * rad), 1, 1, C.steel);
  }
  for (let k = 0; k < 12; k++) {
    const a = (k / 12) * Math.PI * 2 + 0.26;
    const gx = Math.round(cx + Math.cos(a) * rad);
    const gy = Math.round(cy + Math.sin(a) * rad);
    r(gx - 2, gy, 5, 4, C.ink);
    r(gx - 1, gy + 1, 3, 2, k % 2 ? C.amber : C.magenta);
  }
  r(cx - 2, cy - 2, 5, 5, C.ink);
  r(cx - 1, cy - 1, 3, 3, C.brass);
  // the big top
  const tx = 150;
  const top = 46;
  const base = 66;
  const half = 26;
  for (let y = top; y < base; y++) {
    const w = Math.round(((y - top) / (base - top)) * half);
    for (let x = tx - w; x <= tx + w; x++) {
      const stripe = Math.floor((x - tx + 40) / 5) % 2;
      r(x, y, 1, 1, stripe ? C.redDark : C.coatShade);
    }
  }
  r(tx - half, base, half * 2 + 1, FLOOR - base, C.redDark);
  for (let x = tx - half; x <= tx + half; x += 6) r(x, base, 3, FLOOR - base, C.coatShade);
  r(tx - half - 1, base, half * 2 + 3, 2, C.ink);
  r(tx - 4, base + 4, 9, FLOOR - base - 4, C.ink);
  r(tx, top - 8, 1, 8, C.ink);
  r(tx + 1, top - 8, 5, 3, C.green);
  d(X, FLOOR - 6, W, 6, C.night);
}
