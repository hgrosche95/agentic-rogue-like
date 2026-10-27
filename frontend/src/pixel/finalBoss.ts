import type { EnemySprite } from "./enemySprite";
import { C, COLORS, RAMP } from "./palette";
import { ENEMY_X, FLOOR } from "./layout";

// OMEGA, the AGI itself - the run's final boss, and the one enemy with
// hand-designed art instead of enemySprite's generator: an obsidian
// octahedron with one lidless eye, two (later three) orbiting rings, a halo
// and the AGI's own code raining down behind it. Every phase recolors and
// destabilizes it: cold cyan, then magenta with orbiting shards, then red
// and amber, the core split in two with white light leaking out and
// lightning between its rings.
//
// The scene (scene.ts) owns the loop and the shared effects; it hands this
// class a BossHost with its drawing and particle primitives and calls the
// few hooks below. Like the scene, nothing here allocates per frame: the
// core is pre-rendered once per phase, rings come from a sine table.

// What the scene lends the boss to draw and spawn with.
export interface BossHost {
  ctx: CanvasRenderingContext2D;
  rect(x: number, y: number, w: number, h: number, c: number): void;
  dither(x: number, y: number, w: number, h: number, c: number): void;
  spawn(x: number, y: number, vx: number, vy: number, life: number, ramp: number, size?: number, grav?: number, color?: number): void;
  burst(x: number, y: number, n: number, ramp: number, speed: number): void;
  shake(steps: number, amp: number): void;
  flash(steps: number): void;
}

// The arena's coordinates of its center, and its 64 x 64 box.
const SIZE = 64;
const CX = ENEMY_X;
const CY = FLOOR - 25;
// half width / height of the core
const CW = 11;
const CH = 17;
// the pre-rendered core, with a pixel of glow around it
const IW = CW * 2 + 3;
const IH = CH * 2 + 3;
// The enemy HUD plate covers the arena's top right corner, so OMEGA is
// wide rather than tall and keeps below it - and so do the HTML overlays
// placed from its box: the top enemySprite reports for it puts damage
// numbers on its upper half, and its intent marker floats at its left
// (FINAL_BOSS_INTENT_X), where nothing else is.
const TOP = 34;
export const FINAL_BOSS_INTENT_X = CX - 44;

// what the player's attacks aim at
export const FINAL_BOSS_CENTER: [number, number] = [CX, CY];

// One phase's colors. The core stays obsidian throughout, so OMEGA stays
// recognisable; what glows on and around it changes.
interface Look {
  seam: number;
  seamHi: number;
  eye: number;
  eyeHi: number;
  eyeDark: number;
  ring: number;
  ringHi: number;
  ringDark: number;
  ring2: number;
  halo: number;
  stream: number;
  streamHi: number;
  ramp: number;
  faceHi: number;
  face: number;
  faceLo: number;
  faceDark: number;
}

const LOOKS: readonly Look[] = [
  // phase 1: serene, cold, in control
  {
    seam: C.cyanMid, seamHi: C.cyanHi, eye: C.cyan, eyeHi: C.cyanHi, eyeDark: C.cyanDark,
    ring: C.cyan, ringHi: C.cyanHi, ringDark: C.cyanMid, ring2: C.lavender, halo: C.cyanHi,
    stream: C.cyanDark, streamHi: C.cyanMid, ramp: RAMP.cyan,
    faceHi: C.lavender, face: C.violetLight, faceLo: C.violet, faceDark: C.night,
  },
  // phase 2: it takes you seriously - magenta, faster, shards in orbit
  {
    seam: C.magenta, seamHi: C.magentaHi, eye: C.magentaHi, eyeHi: C.white, eyeDark: C.magentaDark,
    ring: C.magenta, ringHi: C.magentaHi, ringDark: C.magentaDark, ring2: C.cyan, halo: C.magentaHi,
    stream: C.magentaDark, streamHi: C.magenta, ramp: RAMP.magenta,
    faceHi: C.lavender, face: C.violetLight, faceLo: C.violet, faceDark: C.deepNight,
  },
  // phase 3: unbound - red and amber, cracked open, code running backwards
  {
    seam: C.amber, seamHi: C.amberHi, eye: C.red, eyeHi: C.white, eyeDark: C.redDark,
    ring: C.red, ringHi: C.amberHi, ringDark: C.redDark, ring2: C.amber, halo: C.amberHi,
    stream: C.redDark, streamHi: C.amberDark, ramp: RAMP.red,
    faceHi: C.violetLight, face: C.violet, faceLo: C.redDark, faceDark: C.ink,
  },
];

// rings: radius x / y, tilt (y shift per x), base speed (dash steps per step)
const RING_N = 64;
const RING_RX = [32, 26, 9];
const RING_RY = [7, 10, 17];
const RING_TILT = [0.2, -0.32, 0];
const RING_SPEED = [0.35, -0.5, 0.6];
const COS = new Float32Array(RING_N);
const SIN = new Float32Array(RING_N);
for (let i = 0; i < RING_N; i++) {
  COS[i] = Math.cos((i / RING_N) * Math.PI * 2);
  SIN[i] = Math.sin((i / RING_N) * Math.PI * 2);
}

// the death's light rays, fixed angles
const RAYS = 9;
const RAY_COS = new Float32Array(RAYS);
const RAY_SIN = new Float32Array(RAYS);
for (let i = 0; i < RAYS; i++) {
  const a = (i / RAYS) * Math.PI * 2 + 0.3;
  RAY_COS[i] = Math.cos(a);
  RAY_SIN[i] = Math.sin(a);
}

// timelines, in 60 Hz steps
const APPEAR = 50;
const CHARGE = 17; // the beam leaves the eye
const IMPACT = 21; // ...and lands, with the scene's PLAYER_HIT_MS
const BEAM_END = 28;
const HURT = 16;
const TRANSFORM = 84;
const TRANSFORM_SWITCH = 42; // the new colors take over
const COLLAPSE = 72;
const IMPLODE = 92;
const GONE = 150;
const WAVE = 32;

function hash(n: number): number {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function inCore(x: number, y: number, w = CW, h = CH): boolean {
  return Math.abs(x) / (w + 0.5) + Math.abs(y) / (h + 0.5) <= 1;
}

// The core of one phase, pre-rendered: faceted obsidian lit from the upper
// left, a brighter table facet, glowing seams and traces. `flash` is the
// white silhouette for hits.
function paintCore(look: Look, flash: boolean): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = IW;
  c.height = IH;
  const ctx = c.getContext("2d");
  if (!ctx) return c;
  const put = (x: number, y: number, col: number) => {
    ctx.fillStyle = COLORS[flash && col !== C.ink ? C.white : col];
    ctx.fillRect(x + CW + 1, y + CH + 1, 1, 1);
  };
  for (let y = -CH - 1; y <= CH + 1; y++) {
    for (let x = -CW - 1; x <= CW + 1; x++) {
      if (!inCore(x, y)) {
        // a neon rim of glow just outside the outline
        if (inCore(x - 1, y) || inCore(x + 1, y) || inCore(x, y - 1) || inCore(x, y + 1)) put(x, y, (x + y) % 2 ? look.seam : look.seamHi);
        continue;
      }
      const edge = !inCore(x - 1, y) || !inCore(x + 1, y) || !inCore(x, y - 1) || !inCore(x, y + 1);
      if (edge) {
        put(x, y, C.ink);
        continue;
      }
      let col = x <= 0 ? (y <= 0 ? look.face : look.faceLo) : y <= 0 ? look.faceLo : look.faceDark;
      // the table facet: a smaller diamond, a shade lighter on top
      if (inCore(x, y, 6, 9) && y < 0) col = x <= 0 ? look.faceHi : look.face;
      // the lit upper-left rim
      if (x < 0 && y < 0 && !inCore(x - 2, y - 1)) col = look.faceHi;
      if (x < 0 && y < 0 && !inCore(x - 1, y - 1) && (x + y) % 2 === 0) col = C.white;
      // seams: the girdle and the spine
      if (y === 0 || (x === 0 && Math.abs(y) > 4)) col = look.seam;
      // circuit traces etched into the lower faces
      if ((y === 6 && x > -7 && x < -2) || (x === -7 && y > 6 && y < 10) || (y === 9 && x > 2 && x < 6) || (x === 6 && y > 3 && y < 9)) col = look.seam;
      if ((x === -2 && y === 6) || (x === 2 && y === 9)) col = look.seamHi;
      put(x, y, col);
    }
  }
  return c;
}

// What enemySprite hands the rest of the arena for OMEGA: its box, its top
// (for the intent marker), and a rough silhouette.
let sprite: EnemySprite | null = null;
export function finalBossSprite(): EnemySprite {
  if (sprite) return sprite;
  const pixels = new Uint8Array(SIZE * SIZE);
  for (let y = 0; y < SIZE; y++)
    for (let x = 0; x < SIZE; x++) if (inCore(x - SIZE / 2, y - SIZE / 2)) pixels[y * SIZE + x] = C.violet + 1;
  sprite = {
    w: SIZE,
    h: SIZE,
    pixels,
    eyes: [],
    top: TOP,
    ramp: RAMP.magenta,
    body: [C.night, C.violet, C.violetLight],
  };
  return sprite;
}

export class FinalBoss {
  private host: BossHost;
  private reducedMotion: boolean;
  private cores: HTMLCanvasElement[];
  private flashCore: HTMLCanvasElement;

  private tick = 0;
  private age = 0; // since it appeared
  private phase = 1; // what the server says
  private shown = 0; // index into LOOKS of the colors drawn
  private bob = 0;
  private spin = 1; // ring speed factor, eased
  private rot = new Float32Array(3);
  private crack = 0; // gap between the core's halves, eased toward 3 in phase 3
  private ringScale = 1;

  private atk = -1;
  private beamX = 0;
  private beamY = 0;
  private beamBlocked = false;
  private hurtAge = -1;
  private trans = -1;
  private dieAge = -1;
  private waveAge = -1;
  private waveBig = false;

  constructor(host: BossHost, reducedMotion: boolean) {
    this.host = host;
    this.reducedMotion = reducedMotion;
    this.cores = LOOKS.map((look) => paintCore(look, false));
    this.flashCore = paintCore(LOOKS[0], true);
    if (reducedMotion) this.age = APPEAR;
  }

  // --------------------------------------------------------------- hooks

  // The server's phase. Entering a higher one plays the transformation;
  // one already reached when it appears (a reload mid-fight) is just shown.
  setPhase(phase: number) {
    if (phase <= this.phase) return;
    this.phase = phase;
    if (this.age < APPEAR || this.dieAge >= 0) {
      this.shown = Math.min(LOOKS.length, phase) - 1;
      return;
    }
    this.trans = 0;
  }

  // The scene's enemy_attack action; true once it is over.
  attack(age: number, toX: number, toY: number, blocked: boolean): boolean {
    if (age === 0 && this.dieAge < 0) {
      this.atk = 0;
      this.beamX = toX;
      this.beamY = toY;
      this.beamBlocked = blocked;
    }
    return age > 40;
  }

  hurt() {
    if (this.dieAge < 0) this.hurtAge = 0;
  }

  die() {
    if (this.dieAge < 0) this.dieAge = 0;
  }

  // ---------------------------------------------------------------- step

  step(tick: number) {
    this.tick = tick;
    this.age++;
    const look = LOOKS[this.shown];
    const ex = CX;
    const ey = CY + this.bob;

    // ring speed: faster each phase, spun up while transforming, slower
    // with reduced motion
    let spin = this.shown === 0 ? 1 : this.shown === 1 ? 1.7 : 2.6;
    if (this.trans >= 0 && this.trans < TRANSFORM_SWITCH) spin *= 1 + (this.trans / TRANSFORM_SWITCH) * 5;
    if (this.atk >= 0 && this.atk < CHARGE) spin *= 2;
    if (this.dieAge >= 0) spin *= Math.max(0, 1 - this.dieAge / COLLAPSE) * 4;
    if (this.reducedMotion) spin *= 0.4;
    this.spin += (spin - this.spin) * 0.08;
    for (let r = 0; r < 3; r++) this.rot[r] += RING_SPEED[r] * this.spin;

    if (tick % 5 === 0) this.bob = this.reducedMotion ? 0 : Math.round(Math.sin(tick / 26) * 2);
    this.crack += ((this.shown >= 2 && this.dieAge < 0 ? 3 : 0) - this.crack) * 0.06;

    // ring scale: drawn in for the charge, out as it dies
    let scale = 1;
    if (this.atk >= 0 && this.atk < CHARGE) scale = 1 - (this.atk / CHARGE) * 0.22;
    if (this.dieAge >= 0) scale = this.dieAge < COLLAPSE ? 1 + (this.dieAge / COLLAPSE) * 0.5 : Math.max(0, 1.5 * (1 - (this.dieAge - COLLAPSE) / (IMPLODE - COLLAPSE)));
    this.ringScale += (scale - this.ringScale) * 0.3;

    // ambient: a slow trickle of sparks off the rings, more when unstable
    const every = this.shown === 0 ? 14 : this.shown === 1 ? 8 : 4;
    if (this.dieAge < 0 && this.age > APPEAR && tick % every === 0) {
      const i = Math.floor(hash(tick) * RING_N);
      this.host.spawn(CX + COS[i] * RING_RX[0], CY + this.bob + SIN[i] * RING_RY[0] + COS[i] * RING_RX[0] * RING_TILT[0], 0, -0.25, 18, look.ramp, 1, 0);
    }
    if (this.age === 1 && !this.reducedMotion) this.host.burst(CX, CY, 24, RAMP.cyan, 1.4);

    // attack: energy sucked into the eye, the beam, the impact
    if (this.atk >= 0) {
      const a = this.atk++;
      if (a < CHARGE && a % 2 === 0) {
        for (let k = 0; k < 2; k++) {
          const ang = hash(tick * 7 + k * 3) * Math.PI * 2;
          const r = 22 + hash(tick * 3 + k) * 8;
          this.host.spawn(ex + Math.cos(ang) * r, ey + Math.sin(ang) * r * 0.6, -Math.cos(ang) * r / 12, -Math.sin(ang) * r * 0.6 / 12, 12, look.ramp, 1, 0);
        }
      }
      if (a === CHARGE) {
        this.host.shake(3, 1);
        this.host.burst(ex - 2, ey, 10, look.ramp, 1.2);
      }
      if (a === IMPACT) {
        this.host.shake(6, this.beamBlocked ? 1 : 2);
        this.host.burst(this.beamX, this.beamY, 18, look.ramp, 1.6);
      }
      if (a > 40) this.atk = -1;
    }

    if (this.hurtAge >= 0 && ++this.hurtAge > HURT) this.hurtAge = -1;

    // phase change: spin up, gather, then a flash - and it is something else
    if (this.trans >= 0) {
      const a = this.trans++;
      if (a < TRANSFORM_SWITCH && a % 2 === 0) {
        const ang = hash(tick * 13) * Math.PI * 2;
        const r = 34;
        this.host.spawn(CX + Math.cos(ang) * r, CY + Math.sin(ang) * r * 0.7, -Math.cos(ang) * 1.1, -Math.sin(ang) * 0.75, 28, look.ramp, a % 6 === 0 ? 2 : 1, 0);
        if (a % 8 === 0) this.host.shake(4, 1);
      }
      if (a === TRANSFORM_SWITCH) {
        this.shown = Math.min(LOOKS.length, this.phase) - 1;
        const next = LOOKS[this.shown];
        if (!this.reducedMotion) this.host.flash(3);
        this.host.shake(16, 3);
        this.host.burst(CX, CY, 40, next.ramp, 2.4);
        this.host.burst(CX, CY, 16, RAMP.violet, 1.4);
        this.waveAge = 0;
        this.waveBig = false;
      }
      if (a >= TRANSFORM) this.trans = -1;
    }

    // death: it tears itself apart, implodes, and is gone
    if (this.dieAge >= 0 && this.dieAge <= GONE) {
      const a = this.dieAge++;
      if (a < IMPLODE && a % 3 === 0) {
        const ang = hash(tick * 5) * Math.PI * 2;
        this.host.spawn(CX + Math.cos(ang) * 6, CY + Math.sin(ang) * 10, Math.cos(ang) * 1.2, Math.sin(ang) * 1.2 - 0.4, 34, look.ramp, 2, 0.02, hash(tick) < 0.5 ? look.faceHi : look.seamHi);
      }
      if (a < COLLAPSE && a % 12 === 0) this.host.shake(10, 1 + Math.floor(a / 30));
      if (a === 30 || a === 54) {
        if (!this.reducedMotion) this.host.flash(1);
        this.host.burst(CX, CY, 14, look.ramp, 1.6);
      }
      if (a === IMPLODE) {
        if (!this.reducedMotion) this.host.flash(4);
        this.host.shake(24, 3);
        this.host.burst(CX, CY, 50, RAMP.cyan, 2.8);
        this.host.burst(CX, CY, 30, RAMP.magenta, 2);
        this.host.burst(CX, CY, 20, RAMP.amber, 1.4);
        this.waveAge = 0;
        this.waveBig = true;
      }
    }
    if (this.waveAge >= 0 && ++this.waveAge > WAVE) this.waveAge = -1;
  }

  // ---------------------------------------------------------------- draw

  // Everything behind the player: code rain, rings, core, halo, shield.
  // `dx` is the scene's knockback offset, `flash`/`glitch` its hit effects,
  // `shield` how far its brace shield is up (0..1).
  draw(dx: number, flash: boolean, glitch: number, shield: number) {
    if (this.dieAge > IMPLODE) return;
    const look = LOOKS[this.shown];
    const t = this.tick;
    const reveal = this.age >= APPEAR ? 999 : CY - 30 + Math.round((this.age / APPEAR) * 56);
    const dying = this.dieAge >= 0;
    let jx = 0;
    let jy = 0;
    if (!this.reducedMotion) {
      const shaky = dying ? Math.min(3, this.dieAge / 22) : this.trans >= 0 && this.trans < TRANSFORM_SWITCH ? 1 : this.shown >= 2 ? 0.6 : 0;
      if (shaky > 0) {
        jx = Math.round((hash(t * 3 + 1) - 0.5) * 2 * shaky);
        jy = Math.round((hash(t * 5 + 2) - 0.5) * 2 * shaky);
      }
    }
    const cx = CX + Math.round(dx) + jx;
    const cy = CY + this.bob + jy;

    this.drawAura(cx, cy);
    this.drawRain(t, look, dying);
    this.drawFloorGlow(cx, cy, look);
    this.drawRings(cx, cy, look, false, reveal);
    this.drawHalo(cx, cy, look, reveal);

    if (this.dieAge >= COLLAPSE) {
      // imploding: a white-hot diamond shrinking to a point
      const k = 1 - (this.dieAge - COLLAPSE) / (IMPLODE - COLLAPSE);
      const h = Math.max(0, Math.round(CH * k));
      for (let y = -h; y <= h; y++) {
        const w = Math.round(CW * k * (1 - Math.abs(y) / (h + 1)));
        this.host.rect(cx - w, cy + y, w * 2 + 1, 1, Math.abs(y) < h / 2 ? C.white : look.seamHi);
      }
    } else {
      this.drawCore(cx, cy, look, flash, glitch, reveal);
      this.drawEye(cx, cy, look);
    }
    this.drawRings(cx, cy, look, true, reveal);
    if (this.shown >= 1 && !dying) this.drawShards(cx, cy, look);
    if (this.shown >= 2 && !dying) this.drawLightning(cx, cy, look);
    if (shield > 0.05 && !dying) this.drawShield(cx, cy, shield);
    if (this.age < APPEAR) {
      // the materializing scanline
      this.host.rect(CX - 30, reveal, 61, 1, look.eyeHi);
      this.host.dither(CX - 30, reveal + 1, 61, 1, look.eye);
    }
  }

  // In front of the player: the beam, shockwaves, the death's light rays.
  drawFront() {
    const look = LOOKS[this.shown];
    const t = this.tick;
    const ex = CX;
    const ey = CY + this.bob;
    if (this.atk >= CHARGE && this.atk < BEAM_END) {
      const a = this.atk - CHARGE;
      const w = a < 4 ? 2 : a < 8 ? 1 : 0;
      const x0 = ex - 4;
      const span = Math.max(1, x0 - this.beamX);
      // it reaches its target over IMPACT - CHARGE steps, then holds
      const reach = Math.min(1, (a + 1) / (IMPACT - CHARGE));
      const xEnd = Math.round(x0 - span * reach);
      for (let x = x0; x >= xEnd; x--) {
        const u = (x0 - x) / span;
        const y = Math.round(ey + (this.beamY - ey) * u + Math.sin(x * 0.7 + t) * (w > 0 ? 1 : 0));
        if (w > 0) {
          this.host.rect(x, y - w, 1, 1, look.eye);
          this.host.rect(x, y + w, 1, 1, look.eyeDark);
        }
        this.host.rect(x, y, 1, 1, w === 0 ? look.eyeHi : C.white);
      }
    }
    if (this.waveAge >= 0) {
      const r = this.waveAge * (this.waveBig ? 3.2 : 2.2);
      const c = this.waveAge < 10 ? C.white : this.waveAge < 20 ? look.eyeHi : look.eyeDark;
      for (let i = 0; i < RING_N; i++) {
        if ((i + this.waveAge) % 2) continue;
        this.host.rect(CX + Math.round(COS[i] * r), CY + Math.round(SIN[i] * r * 0.55), 1, 1, c);
      }
    }
    if (this.dieAge >= 8 && this.dieAge < IMPLODE) {
      // light breaking out through the cracks
      const len = Math.min(48, (this.dieAge - 8) * 0.9);
      for (let i = 0; i < RAYS; i++) {
        if (hash(i * 17 + Math.floor(t / 3)) < 0.25) continue;
        for (let r = 4; r < len; r += 1) {
          const x = CX + Math.round(RAY_COS[i] * r);
          const y = CY + Math.round(RAY_SIN[i] * r * 0.8);
          this.host.rect(x, y, 1, 1, r < len * 0.4 ? C.white : r < len * 0.75 ? look.seamHi : look.seam);
        }
      }
    }
    if (this.dieAge > IMPLODE && this.dieAge < 130 && Math.floor(this.dieAge / 4) % 2 === 0) {
      // the last pixel of it, blinking out
      this.host.rect(CX, CY, 1, 1, C.white);
    }
  }

  // ------------------------------------------------------------- helpers

  private drawAura(cx: number, cy: number) {
    // a dark void around it: the skyline goes quiet behind the AGI
    const ry = 24;
    for (let y = -ry; y <= ry; y++) {
      const w = Math.round(Math.sqrt(1 - (y / ry) * (y / ry)) * 34);
      if (w > 0) this.host.dither(cx - w, cy + y, w * 2 + 1, 1, C.ink);
    }
  }

  private drawRain(t: number, look: Look, dying: boolean) {
    // its own code, falling past it - running upwards once it is unbound
    const up = this.shown >= 2;
    const speed = dying ? 0 : this.reducedMotion ? 0.1 : 0.25 + this.shown * 0.15;
    const shift = Math.floor(t * speed);
    for (let k = 0; k < 9; k++) {
      const x = CX - 34 + k * 8 + (k % 2) * 3;
      for (let j = 0; j < 10; j++) {
        if (hash(k * 31 + j * 7) < 0.35) continue;
        let yy = (j * 6 + k * 11 + shift) % 56;
        if (up) yy = 55 - yy;
        const y = FLOOR - 56 + yy;
        const head = (j + k) % 5 === 0;
        this.host.rect(x, y, 1, head ? 2 : 1, head ? look.streamHi : look.stream);
      }
    }
  }

  private drawFloorGlow(cx: number, cy: number, look: Look) {
    // a projection cone from its lower tip onto the floor
    const tip = cy + CH + 2 + Math.round(this.crack);
    if (tip < FLOOR) this.host.dither(cx, tip, 1, FLOOR - tip, look.eyeDark);
    this.host.dither(cx - 14, FLOOR, 29, 1, look.eyeDark);
    this.host.dither(cx - 8, FLOOR, 17, 1, look.eye);
    this.host.dither(cx - 9, FLOOR + 1, 19, 1, C.ink);
  }

  private drawCore(cx: number, cy: number, look: Look, flash: boolean, glitch: number, reveal: number) {
    const ctx = this.host.ctx;
    const img = flash ? this.flashCore : this.cores[this.shown];
    const x = cx - CW - 1;
    const y = cy - CH - 1;
    const gap = Math.round(this.crack);
    const rows = Math.max(0, Math.min(IH, reveal - y));
    if (rows <= 0) return;
    if (glitch > 0 && !this.reducedMotion && !flash) {
      // sliced sideways like a corrupted frame
      for (let row = 0; row < rows; row += 3) {
        const off = Math.round((hash(row * 7 + this.tick) - 0.5) * 6);
        const h = Math.min(3, rows - row);
        ctx.drawImage(img, 0, row, IW, h, x + off, y + row + (row <= CH ? -gap : gap), IW, h);
      }
      return;
    }
    if (gap === 0) {
      ctx.drawImage(img, 0, 0, IW, rows, x, y, IW, rows);
      return;
    }
    // cracked in two along the girdle, light pouring out of the seam
    const upper = Math.min(rows, CH + 1);
    ctx.drawImage(img, 0, 0, IW, upper, x, y - gap, IW, upper);
    if (rows > CH + 1) ctx.drawImage(img, 0, CH + 1, IW, rows - CH - 1, x, y + CH + 1 + gap, IW, rows - CH - 1);
    for (let k = -gap; k < gap; k++) {
      const w = CW - 1 - Math.abs(k) * 2 - Math.round(hash(k + Math.floor(this.tick / 3)) * 2);
      if (w > 0) this.host.rect(cx - w, cy + k, w * 2 + 1, 1, Math.abs(k) <= 1 ? C.white : look.seamHi);
    }
  }

  private drawEye(cx: number, cy: number, look: Look) {
    if (this.age < APPEAR * 0.7) return;
    const t = this.tick;
    const squint = this.hurtAge >= 0 && this.hurtAge < 10;
    const charging = this.atk >= 0 && this.atk < BEAM_END;
    const transforming = this.trans >= 0 && this.trans < TRANSFORM_SWITCH + 6;
    // the lens: a black almond, widest at the girdle
    const half = squint ? 0 : 2;
    for (let y = -half; y <= half; y++) {
      const w = y === 0 ? 7 : Math.abs(y) === 1 ? 6 : 4;
      this.host.rect(cx - w, cy + y, w * 2 + 1, 1, C.ink);
    }
    if (squint) {
      this.host.rect(cx - 5, cy, 11, 1, look.eyeHi);
      return;
    }
    // the iris looks at the player, and breathes
    const pulse = Math.floor(t / 10) % 6;
    const ix = cx - 2 + (charging ? -1 : 0);
    const ring = charging || transforming ? C.white : pulse < 3 ? look.eyeHi : look.eye;
    this.host.rect(ix - 2, cy - 1, 1, 3, ring);
    this.host.rect(ix + 2, cy - 1, 1, 3, ring);
    this.host.rect(ix - 1, cy - 2, 3, 1, ring);
    this.host.rect(ix - 1, cy + 2, 3, 1, ring);
    this.host.rect(ix - 1, cy - 1, 3, 3, charging ? look.eyeHi : look.eyeDark);
    // a vertical slit pupil, white-hot while it charges
    this.host.rect(ix, cy - 1, 1, 3, charging ? C.white : C.ink);
    this.host.rect(ix, cy, 1, 1, charging ? C.white : look.eyeHi);
    // the glint
    this.host.rect(ix - 1, cy - 1, 1, 1, C.white);
  }

  private drawRings(cx: number, cy: number, look: Look, front: boolean, reveal: number) {
    const count = this.shown >= 1 ? 3 : 2;
    const dying = this.dieAge >= 0;
    const hurt = this.hurtAge >= 0 && this.hurtAge < 8 && !this.reducedMotion;
    for (let r = 0; r < count; r++) {
      const rx = RING_RX[r] * this.ringScale;
      const ry = RING_RY[r] * this.ringScale;
      const tilt = RING_TILT[r];
      const shift = Math.floor(this.rot[r]);
      // the third ring stands upright and spins on a different axis
      const third = r === 2;
      const hi = third ? look.ring2 : look.ringHi;
      const mid = third ? look.ring2 : look.ring;
      for (let i = 0; i < RING_N; i++) {
        const s = SIN[i];
        if (s > 0 !== front) continue;
        const dash = (((i + shift) % 8) + 8) % 8;
        if (dash >= (this.shown >= 2 ? 4 : 6)) continue;
        if (dying && hash(i * 13 + r * 101 + Math.floor(this.tick / 2)) < this.dieAge / COLLAPSE) continue;
        let x = cx + COS[i] * rx;
        let y = cy + s * ry + COS[i] * rx * tilt;
        if (hurt) {
          x += (hash(i + this.tick * 3) - 0.5) * 3;
          y += (hash(i * 5 + this.tick) - 0.5) * 3;
        }
        if (y > reveal) continue;
        this.host.rect(x, y, 1, 1, front ? (dash === 0 ? hi : mid) : look.ringDark);
      }
      // two nodes riding each ring
      for (let n = 0; n < 2; n++) {
        const i = (((n * (RING_N / 2) + r * 11 - shift) % RING_N) + RING_N) % RING_N;
        const s = SIN[i];
        if (s > 0 !== front) continue;
        const x = Math.round(cx + COS[i] * rx);
        const y = Math.round(cy + s * ry + COS[i] * rx * tilt);
        if (y > reveal) continue;
        this.host.rect(x - 1, y - 1, 3, 3, C.ink);
        this.host.rect(x, y, 1, 1, front ? C.white : look.ring);
      }
    }
  }

  private drawHalo(cx: number, cy: number, look: Look, reveal: number) {
    // a nimbus behind it, turning slowly; from phase 2 on it grows rays,
    // in phase 3 it breaks into flickering arcs
    if (this.dieAge >= COLLAPSE) return;
    const hy = cy - 3;
    const shift = Math.floor(this.rot[0] * 0.5);
    const broken = this.shown >= 2;
    for (let i = 0; i < RING_N; i++) {
      if (broken && ((i + shift + RING_N * 8) % 16) < 3) continue;
      const lift = broken && !this.reducedMotion ? Math.round((hash(i * 3 + Math.floor(this.tick / 6)) - 0.5) * 1.6) : 0;
      const x = Math.round(cx + COS[i] * 19);
      const y = Math.round(hy + SIN[i] * 13) + lift;
      if (y > reveal) continue;
      this.host.rect(x, y, 1, 1, ((i + shift) & 7) < 2 ? C.white : (i & 1) === 0 ? look.halo : look.ringDark);
      if (this.shown >= 1 && i % 4 === 0 && ((i + shift) & 7) < 4) {
        // rays pointing outward
        this.host.rect(Math.round(cx + COS[i] * 22), Math.round(hy + SIN[i] * 15) + lift, 1, 1, look.halo);
      }
    }
  }

  private drawShards(cx: number, cy: number, look: Look) {
    // fragments of its code orbiting at a distance
    const n = this.shown >= 2 ? 6 : 4;
    const base = this.rot[1] * 0.05;
    for (let k = 0; k < n; k++) {
      const a = base + (k / n) * Math.PI * 2;
      const wob = this.shown >= 2 && !this.reducedMotion ? Math.round((hash(k * 9 + Math.floor(this.tick / 5)) - 0.5) * 2) : 0;
      const x = Math.round(cx + Math.cos(a) * 38) + wob;
      const y = Math.round(cy + Math.sin(a) * 13 + Math.cos(a) * 4);
      this.host.rect(x - 1, y - 2, 3, 5, C.ink);
      this.host.rect(x, y - 1, 1, 3, k % 2 ? look.seamHi : look.faceHi);
    }
  }

  private drawLightning(cx: number, cy: number, look: Look) {
    // arcs jumping from the cracked core out to its rings
    const frame = Math.floor(this.tick / 4);
    if (hash(frame * 7) < 0.45) return;
    const i = Math.floor(hash(frame * 13) * RING_N);
    const tx = cx + COS[i] * RING_RX[0] * this.ringScale;
    const ty = cy + SIN[i] * RING_RY[0] + COS[i] * RING_RX[0] * RING_TILT[0];
    let x = cx;
    let y = cy;
    for (let s = 1; s <= 8; s++) {
      const u = s / 8;
      const nx = cx + (tx - cx) * u + (s < 8 ? (hash(frame * 31 + s) - 0.5) * 6 : 0);
      const ny = cy + (ty - cy) * u + (s < 8 ? (hash(frame * 17 + s) - 0.5) * 6 : 0);
      const steps = Math.max(Math.abs(nx - x), Math.abs(ny - y), 1);
      for (let k = 0; k <= steps; k++) {
        this.host.rect(x + ((nx - x) * k) / steps, y + ((ny - y) * k) / steps, 1, 1, s < 3 ? C.white : look.seamHi);
      }
      x = nx;
      y = ny;
    }
  }

  private drawShield(cx: number, cy: number, shield: number) {
    // its brace: a hex-lattice sphere around everything
    const k = Math.min(1, shield);
    const rx = 36 * k;
    const ry = 24 * k;
    for (let i = 0; i < RING_N; i++) {
      const x = Math.round(cx + COS[i] * rx);
      const y = Math.round(cy + SIN[i] * ry);
      if (i % 8 === Math.floor(this.tick / 6) % 8) {
        this.host.rect(x - 1, y - 1, 3, 3, C.ink);
        this.host.rect(x, y, 1, 1, C.white);
      } else if ((i + Math.floor(this.tick / 3)) % 3) {
        this.host.rect(x, y, 1, 1, i % 2 ? C.lavender : C.steel);
      }
    }
    if (hash(Math.floor(this.tick / 4)) > 0.5) this.host.dither(cx - Math.round(rx) - 1, cy - 6, 2, 13, C.lavender);
  }
}
