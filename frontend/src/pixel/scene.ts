import type { CardType } from "../api";
import { enemySprite, type EnemySpec, type EnemySprite } from "./enemySprite";
import { C, COLORS, RAMPS, RAMP } from "./palette";
import { ENEMY_X, FLOOR, HEIGHT, KEYBOARD, MONITOR, PLAYER_X, RIFT_X, WIDTH } from "./layout";

// The pixel arena: everything is drawn into a WIDTH x HEIGHT canvas, one
// palette color per pixel, at integer coordinates only. The simulation steps
// at a fixed 60 Hz (step), drawing happens once per animation frame (draw).
// Poses are eased every step but only shown at ~12 fps, so motion reads like
// a hand-animated sprite. The loop allocates nothing: particles, projectiles
// and running actions live in preallocated pools.

export type ArenaEvent =
  | CardType
  | "enemy_attack"
  | "enemy_attack_blocked"
  | "enemy_brace"
  | "daemon"
  | "enemy_hurt"
  | "player_hurt"
  | "player_healed"
  | "enemy_die";

export interface SceneStatus {
  typing: boolean;
  block: number;
  armor: number;
  enemyBlock: number;
  // permanent cards lying on the field
  turrets: number;
  amplifiers: number;
  fortify: number;
}

const EV: Record<ArenaEvent, number> = {
  attack: 1,
  final_strike: 2,
  block: 3,
  heal: 4,
  amplifier: 5,
  armor: 6,
  draw_bonus: 7,
  draw: 8,
  retrieve: 9,
  restore: 10,
  reboot: 11,
  damage_boost: 12,
  turret: 13,
  fortify: 14,
  enemy_attack: 20,
  enemy_attack_blocked: 21,
  enemy_brace: 22,
  daemon: 23,
  enemy_hurt: 24,
  player_hurt: 25,
  player_healed: 26,
  enemy_die: 27,
};

const STEP_MS = 1000 / 60;
// the pose is re-sampled every POSE_EVERY steps: ~12 fps sprite animation
const POSE_EVERY = 5;
// steps until a card's hit lands (hooks/useLagged ENEMY_HIT_MS = 550 ms)
const HIT_AT = 33;

const MAX_PARTICLES = 700;
const MAX_PROJECTILES = 24;
const MAX_ACTIONS = 16;
const MAX_PULSES = 6;

// the cable from the keyboard down the pult and along the floor into the rift
const CABLE: [number, number][] = [];
{
  const pts: [number, number][] = [
    [KEYBOARD.x + KEYBOARD.w, KEYBOARD.y + 2],
    [KEYBOARD.x + KEYBOARD.w + 2, KEYBOARD.y + 5],
    [KEYBOARD.x + KEYBOARD.w + 2, FLOOR - 1],
    [KEYBOARD.x + KEYBOARD.w + 4, FLOOR + 1],
    [RIFT_X - 3, FLOOR + 1],
  ];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const n = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
    for (let k = 0; k < n; k++) CABLE.push([Math.round(x0 + ((x1 - x0) * k) / n), Math.round(y0 + ((y1 - y0) * k) / n)]);
  }
}

// cheap deterministic noise for flicker and jitter
function hash(n: number): number {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function newCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

export class PixelScene {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private bg: HTMLCanvasElement;
  private patterns: (CanvasPattern | null)[] = [];
  private reducedMotion: boolean;

  private tick = 0;
  shakeX = 0;
  shakeY = 0;
  private shake = 0;
  private shakeAmp = 0;

  private status: SceneStatus = { typing: false, block: 0, armor: 0, enemyBlock: 0, turrets: 0, amplifiers: 0, fortify: 0 };
  private playerVisible = true;
  private night = false;

  // -- enemy
  private enemy: EnemySprite | null = null;
  private enemyCanvas: HTMLCanvasElement | null = null;
  private enemyFlashCanvas: HTMLCanvasElement | null = null;
  private enemyDead = false;
  private enemyAppear = 0;
  private enemyShield = 0; // 0..1, eased toward enemyBlock > 0

  // -- player pose (eased) and what is shown (sampled at ~12 fps)
  private hand = { fx: 14, fy: -24, bx: 11, by: -23 };
  private shown = { fx: 14, fy: -24, bx: 11, by: -23, lean: 0, tilt: 0, bob: 0 };
  private lean = 0;
  private tilt = 0;
  private item = 0; // 0 none, 1 flask, 2 raygun
  private playerFlash = 0;
  private playerKnock = 0;
  private rim = 0; // rim light strength
  private rimColor: number = C.cyan;
  private wall = 0; // firewall 0..1
  private drones = 0; // drones shown, eased toward status.turrets
  private tower = 0; // mainframe slabs 0..1
  private coilSurge = 0;
  private flash = 0;
  private sweep = -1;
  private riftFlare = 0;
  private keysLit = 0;

  // -- enemy pose
  private ex = 0;
  private enemyFlash = 0;
  private glitch = 0;

  // -- pools
  private px = new Float32Array(MAX_PARTICLES);
  private py = new Float32Array(MAX_PARTICLES);
  private pvx = new Float32Array(MAX_PARTICLES);
  private pvy = new Float32Array(MAX_PARTICLES);
  private pg = new Float32Array(MAX_PARTICLES);
  private plife = new Int16Array(MAX_PARTICLES);
  private pmax = new Int16Array(MAX_PARTICLES);
  private pramp = new Int8Array(MAX_PARTICLES);
  private pcolor = new Int16Array(MAX_PARTICLES);
  private psize = new Uint8Array(MAX_PARTICLES);
  private pnext = 0;

  private jx0 = new Float32Array(MAX_PROJECTILES);
  private jy0 = new Float32Array(MAX_PROJECTILES);
  private jx1 = new Float32Array(MAX_PROJECTILES);
  private jy1 = new Float32Array(MAX_PROJECTILES);
  private jage = new Int16Array(MAX_PROJECTILES);
  private jdur = new Int16Array(MAX_PROJECTILES);
  private jramp = new Int8Array(MAX_PROJECTILES);
  private jsize = new Uint8Array(MAX_PROJECTILES);
  private jarc = new Float32Array(MAX_PROJECTILES);
  private jburst = new Uint8Array(MAX_PROJECTILES); // particles on arrival
  private jcard = new Uint8Array(MAX_PROJECTILES); // drawn as a little data card
  private jlive = new Uint8Array(MAX_PROJECTILES);

  private akind = new Int8Array(MAX_ACTIONS);
  private aage = new Int16Array(MAX_ACTIONS);
  private aparam = new Int16Array(MAX_ACTIONS);

  private pulseAge = new Int16Array(MAX_PULSES).fill(-1);

  // stars of the machine world's sky
  private stars = new Int16Array(48);

  constructor() {
    this.canvas = newCanvas(WIDTH, HEIGHT);
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("no 2d context");
    this.ctx = ctx;
    ctx.imageSmoothingEnabled = false;
    this.reducedMotion = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    for (let i = 0; i < this.stars.length; i += 2) {
      this.stars[i] = RIFT_X + 6 + Math.floor(hash(i * 7 + 1) * (WIDTH - RIFT_X - 8));
      this.stars[i + 1] = 1 + Math.floor(hash(i * 13 + 5) * 44);
    }
    this.bg = this.paintBackground();
  }

  // ------------------------------------------------------------------ API

  setEnemy(spec: EnemySpec | null) {
    if (!spec) {
      this.enemy = null;
      return;
    }
    const sprite = enemySprite(spec);
    if (sprite === this.enemy) return;
    this.enemy = sprite;
    this.enemyCanvas = this.spriteCanvas(sprite, false);
    this.enemyFlashCanvas = this.spriteCanvas(sprite, true);
    this.enemyDead = false;
    this.enemyAppear = 24;
  }

  setStatus(status: SceneStatus) {
    this.status = status;
  }

  setPlayerVisible(visible: boolean) {
    this.playerVisible = visible;
  }

  setNight(night: boolean) {
    this.night = night;
  }

  trigger(event: ArenaEvent, delayMs = 0, param = 0) {
    const kind = EV[event];
    // reuse a free slot, else the oldest
    let slot = 0;
    let oldest = -1;
    for (let i = 0; i < MAX_ACTIONS; i++) {
      if (this.akind[i] === 0) {
        slot = i;
        oldest = -2;
        break;
      }
      if (this.aage[i] > oldest) {
        oldest = this.aage[i];
        slot = i;
      }
    }
    this.akind[slot] = kind;
    // the next step brings it to age 0
    this.aage[slot] = -Math.round(delayMs / STEP_MS) - 1;
    this.aparam[slot] = param;
  }

  // the enemy's head, for the intent marker - in logical pixels
  enemyTop(): number {
    if (!this.enemy) return 0;
    return FLOOR - this.enemy.h + this.enemy.top;
  }

  // --------------------------------------------------------------- update

  step() {
    this.tick++;
    const t = this.tick;

    // default pose: resting on the keys, hammering them while typing
    let fx = 14;
    let fy = -24;
    let bx = 11;
    let by = -23;
    let lean = 0;
    let tilt = 0;
    let item = 0;
    if (this.status.typing) {
      const beat = Math.floor(t / 4) % 2;
      fy = beat ? -26 : -24;
      by = beat ? -23 : -25;
      this.keysLit = 4;
    }

    let rimTarget = this.status.armor > 0 ? 0.6 : 0;
    this.rimColor = C.cyan;

    for (let i = 0; i < MAX_ACTIONS; i++) {
      const kind = this.akind[i];
      if (kind === 0) continue;
      const age = ++this.aage[i];
      if (age < 0) continue;
      const done = this.runAction(kind, age, this.aparam[i]);
      if (done) this.akind[i] = 0;

      // poses of the running player actions
      if (age > 60) continue;
      switch (kind) {
        case EV.attack:
        case EV.damage_boost:
          if (age < 12) {
            const beat = Math.floor(age / 2) % 2;
            fy = beat ? -27 : -23;
            by = beat ? -23 : -26;
            lean = 1;
          }
          break;
        case EV.final_strike:
          if (age < 48) {
            fx = 16;
            fy = -27;
            item = 2;
            lean = age > 26 && age < 32 ? -1 : 1;
            rimTarget = Math.max(rimTarget, age < 26 ? age / 26 : 1);
            this.rimColor = C.red;
          }
          break;
        case EV.block:
          if (age < 40) {
            bx = 11;
            by = -32;
            lean = 1;
          }
          break;
        case EV.heal:
          if (age < 36) {
            fx = 7;
            fy = age < 8 ? -28 : -31;
            item = 1;
            tilt = age > 8 && age < 30 ? -1 : 0;
            lean = -1;
          }
          break;
        case EV.amplifier:
          if (age < 30) {
            fy = age % 6 < 3 ? -27 : -22;
            by = -30;
            bx = 4;
            rimTarget = 1;
            this.rimColor = C.magentaHi;
          }
          break;
        case EV.armor:
        case EV.fortify:
          if (age < 36) {
            bx = 6;
            by = -30;
            fx = 12;
            fy = -30;
            rimTarget = 1;
          }
          break;
        case EV.draw:
        case EV.draw_bonus:
          if (age < 40) {
            bx = 8;
            by = -31;
            tilt = -1;
          }
          break;
        case EV.retrieve:
        case EV.restore:
        case EV.reboot:
          if (age < 40) {
            fx = 14;
            fy = -24 - (Math.floor(age / 3) % 2);
            tilt = age % 20 < 10 ? 1 : 0;
            rimTarget = Math.max(rimTarget, 0.7);
            this.rimColor = C.violetLight;
          }
          break;
        case EV.turret:
          if (age < 30) {
            bx = 9;
            by = -30;
          }
          break;
        case EV.player_hurt:
          if (age < 14) {
            fx = 10;
            fy = -21;
            bx = 7;
            by = -20;
            lean = -2;
          }
          break;
      }
    }

    // ease the pose, then quantize it to the sprite's ~12 fps
    const h = this.hand;
    h.fx += (fx - h.fx) * 0.35;
    h.fy += (fy - h.fy) * 0.35;
    h.bx += (bx - h.bx) * 0.35;
    h.by += (by - h.by) * 0.35;
    this.lean += (lean - this.lean) * 0.3;
    this.tilt += (tilt - this.tilt) * 0.3;
    this.item = item;
    this.rim += (rimTarget - this.rim) * 0.1;
    if (t % POSE_EVERY === 0 || this.playerFlash > 0) {
      const s = this.shown;
      s.fx = Math.round(h.fx);
      s.fy = Math.round(h.fy);
      s.bx = Math.round(h.bx);
      s.by = Math.round(h.by);
      s.lean = Math.round(this.lean);
      s.tilt = Math.round(this.tilt);
      s.bob = Math.floor(t / 30) % 2;
    }

    // persistent status visuals ease in and out
    this.wall += ((this.status.block > 0 ? 1 : 0) - this.wall) * 0.08;
    this.drones += (this.status.turrets - this.drones) * 0.1;
    this.tower += ((this.status.fortify > 0 ? 1 : 0) - this.tower) * 0.06;
    this.enemyShield += ((this.status.enemyBlock > 0 && !this.enemyDead ? 1 : 0) - this.enemyShield) * 0.12;

    if (this.playerFlash > 0) this.playerFlash--;
    if (this.playerKnock > 0) this.playerKnock--;
    if (this.enemyFlash > 0) this.enemyFlash--;
    if (this.glitch > 0) this.glitch--;
    if (this.flash > 0) this.flash--;
    if (this.riftFlare > 0) this.riftFlare--;
    if (this.keysLit > 0) this.keysLit--;
    if (this.coilSurge > 0) this.coilSurge--;
    if (this.enemyAppear > 0) this.enemyAppear--;
    this.ex *= 0.8;
    if (Math.abs(this.ex) < 0.3) this.ex = 0;
    if (this.sweep >= 0) this.sweep += 5;
    if (this.sweep > HEIGHT + 10) this.sweep = -1;

    if (this.shake > 0) {
      this.shake--;
      const a = this.reducedMotion ? 0 : this.shakeAmp;
      this.shakeX = Math.round((hash(t * 3) * 2 - 1) * a);
      this.shakeY = Math.round((hash(t * 5 + 1) * 2 - 1) * a);
    } else {
      this.shakeX = 0;
      this.shakeY = 0;
    }

    // ambient life: coil arcs, rift sparks, the amplifier's hum
    const coilRate = this.status.amplifiers > 0 || this.coilSurge > 0 ? 3 : 14;
    if (!this.night && t % coilRate === 0) {
      this.spawn(13 + hash(t) * 6, 36 + hash(t + 1) * 4, (hash(t + 2) - 0.5) * 0.8, -0.3 - hash(t + 3) * 0.5, 14, this.coilSurge > 0 ? RAMP.magenta : RAMP.amber, 1, 0.02);
    }
    if (t % 9 === 0 && !this.night) {
      this.spawn(RIFT_X + (hash(t * 7) - 0.5) * 4, hash(t * 11) * FLOOR, (hash(t * 13) - 0.5) * 0.6, -0.2, 20, hash(t) < 0.5 ? RAMP.cyan : RAMP.amber, 1, 0);
    }
    if (this.wall > 0.5 && t % 7 === 0) {
      this.spawn(90 + hash(t) * 4, FLOOR - hash(t * 3) * 30, 0, -0.35, 16, RAMP.amber, 1, 0);
    }

    this.stepParticles();
    this.stepProjectiles();
    for (let i = 0; i < MAX_PULSES; i++) {
      if (this.pulseAge[i] < 0) continue;
      this.pulseAge[i] += 3;
      if (this.pulseAge[i] >= CABLE.length) {
        this.pulseAge[i] = -1;
        this.riftFlare = 8;
        this.burst(RIFT_X, FLOOR - 2, 8, RAMP.cyan, 1.2);
      }
    }
  }

  private enemyCenter(): [number, number] {
    const e = this.enemy;
    if (!e) return [ENEMY_X, FLOOR - 14];
    return [ENEMY_X, FLOOR - e.h + Math.round((e.top + e.h) / 2)];
  }

  private shakeFor(steps: number, amp: number) {
    this.shake = Math.max(this.shake, steps);
    this.shakeAmp = Math.max(this.shake > 0 ? this.shakeAmp : 0, amp);
  }

  // One step of a running action; returns true once it is over.
  private runAction(kind: number, age: number, param: number): boolean {
    const [ecx, ecy] = this.enemyCenter();
    const chestX = PLAYER_X + 2;
    const chestY = FLOOR - 18;
    switch (kind) {
      // -- cards
      case EV.attack: {
        if (age < 12 && age % 2 === 0) this.keysLit = 3;
        if (age === 2) this.pulse();
        if (age === 16) this.fire(RIFT_X + 2, FLOOR - 26, ecx - 4, ecy, HIT_AT - 16, RAMP.cyan, 3, 8, 18);
        if (age === HIT_AT) this.shakeFor(4, 1);
        return age > HIT_AT + 10;
      }
      case EV.final_strike: {
        const tipX = PLAYER_X + 22;
        const tipY = FLOOR - 28;
        if (age < 26 && age % 2 === 0) {
          // sparks spiral in to the muzzle
          const a = age * 0.9;
          const r = 12 - age * 0.35;
          this.spawn(tipX + Math.cos(a) * r, tipY + Math.sin(a) * r, -Math.cos(a) * 0.5 - Math.sin(a) * 0.3, -Math.sin(a) * 0.5 + Math.cos(a) * 0.3, 14, RAMP.red, 1, 0);
        }
        if (age === 26) {
          this.flash = 3;
          this.shakeFor(12, 2);
          this.burst(tipX, tipY, 12, RAMP.red, 1.6);
        }
        if (age === HIT_AT) {
          this.burst(ecx, ecy, 36, RAMP.red, 2.4);
          this.burst(ecx, ecy, 18, RAMP.amber, 1.4);
        }
        return age > 56;
      }
      case EV.damage_boost: {
        if (age === 2) this.pulse();
        if (age === 16) {
          // the load spread three ways out of the rift
          for (let k = -1; k <= 1; k++) this.fire(RIFT_X + 2, FLOOR - 26, ecx - 6, ecy + k * 10, 14 + Math.abs(k) * 3, RAMP.cyan, 1, 6 + k * 6, 6);
        }
        return age > 50;
      }
      case EV.block: {
        if (age >= 4 && age < 20) {
          const y = FLOOR - Math.round(((age - 4) / 16) * 30);
          this.spawn(89 + hash(age) * 5, y, (hash(age * 3) - 0.5) * 0.8, -0.4, 12, RAMP.amber, 1, 0.02);
        }
        return age > 40;
      }
      case EV.heal: {
        if (age > 8 && age < 30 && age % 3 === 0) {
          this.spawn(PLAYER_X + 8 + hash(age) * 3, FLOOR - 34, (hash(age * 5) - 0.5) * 0.3, -0.4, 22, RAMP.green, 1, -0.005);
        }
        if (age === 22) {
          for (let k = 0; k < 16; k++) {
            const a = (k / 16) * Math.PI * 2;
            this.spawn(chestX + Math.cos(a) * 10, chestY + Math.sin(a) * 14, 0, -0.5 - hash(k) * 0.4, 26, RAMP.green, k % 3 === 0 ? 3 : 1, 0);
          }
        }
        return age > 44;
      }
      case EV.amplifier: {
        if (age === 0) this.coilSurge = 40;
        if (age === 6) {
          this.burst(16, 36, 18, RAMP.magenta, 1.6);
          this.burst(PLAYER_X - 8, FLOOR - 32, 10, RAMP.amber, 1.1);
          this.shakeFor(4, 1);
        }
        if (age > 6 && age < 30 && age % 4 === 0) {
          // an arc jumping from the coil over to his pack
          this.fire(16, 36, PLAYER_X - 8, FLOOR - 32, 6, RAMP.magenta, 1, -4, 0);
        }
        return age > 40;
      }
      case EV.armor: {
        if (age < 30 && age % 2 === 0) {
          // lock glyphs orbiting in, tighter every turn
          const a = age * 0.5;
          const r = 16 - age * 0.35;
          this.spawn(chestX + Math.cos(a) * r, chestY + Math.sin(a) * r * 1.3, 0, 0, 8, RAMP.cyan, 2, 0);
        }
        if (age === 30) this.burst(chestX, chestY, 20, RAMP.cyan, 1.3);
        return age > 44;
      }
      case EV.fortify: {
        if (age < 24 && age % 3 === 0) this.spawn(40 + hash(age) * 10, FLOOR, 0, -0.6, 18, RAMP.steel, 1, 0);
        return age > 40;
      }
      case EV.draw:
      case EV.draw_bonus: {
        // data cards drop out of the monitor into his hands
        const cards = Math.min(4, Math.max(1, param));
        for (let k = 0; k < cards; k++) {
          if (age === 2 + k * 5) {
            this.fire(MONITOR.x + MONITOR.w / 2 - 20 + k * 6, MONITOR.y + MONITOR.h, PLAYER_X + 8, FLOOR - 30, 16, RAMP.cyan, 2, 10, 4, true);
          }
        }
        return age > 50;
      }
      case EV.retrieve:
      case EV.restore:
      case EV.reboot: {
        // time runs backwards: sparks fall *in* toward him
        if (age < 30 && age % 2 === 0) {
          const a = hash(age * 17) * Math.PI * 2;
          const r = 22;
          this.spawn(chestX + Math.cos(a) * r, chestY + Math.sin(a) * r, -Math.cos(a) * 0.9, -Math.sin(a) * 0.9, 22, RAMP.violet, 1, 0);
        }
        if (kind === EV.reboot && age === 4) {
          this.sweep = 0;
          this.flash = 2;
        }
        return age > 44;
      }
      case EV.turret: {
        const slot = Math.max(0, Math.round(this.status.turrets) - 1);
        const [dx, dy] = this.dronePos(slot);
        if (age < 20 && age % 2 === 0) {
          const a = hash(age * 5) * Math.PI * 2;
          this.spawn(dx + Math.cos(a) * 10, dy + Math.sin(a) * 10, -Math.cos(a) * 0.5, -Math.sin(a) * 0.5, 20, RAMP.red, 1, 0);
        }
        return age > 30;
      }

      // -- the enemy's turn
      case EV.enemy_attack:
      case EV.enemy_attack_blocked: {
        if (age < 8) this.ex = 3;
        if (age === 8) {
          this.ex = -7;
          const e = this.enemy;
          const ramp = e ? e.ramp : RAMP.red;
          const toX = kind === EV.enemy_attack_blocked && this.wall > 0.3 ? 93 : chestX + 2;
          this.fire(ecx - 10, ecy + 3, toX, chestY, 13, ramp, 3, 4, 18);
        }
        if (age === 21) this.shakeFor(6, kind === EV.enemy_attack_blocked ? 1 : 2);
        return age > 40;
      }
      case EV.enemy_brace: {
        if (age < 12 && age % 2 === 0) this.spawn(ENEMY_X - 24, FLOOR - hash(age) * 30, 0, -0.3, 14, RAMP.steel, 1, 0);
        return age > 20;
      }
      case EV.daemon: {
        if (age === 0) {
          const n = Math.round(this.drones);
          for (let k = 0; k < n; k++) {
            const [dx, dy] = this.dronePos(k);
            this.fire(dx + 3, dy + 1, ecx - 4, ecy - 4, 10 + k * 2, RAMP.red, 1, 2, 8);
          }
        }
        return age > 20;
      }
      case EV.enemy_hurt: {
        if (age === 0) {
          this.enemyFlash = 4;
          this.glitch = 12;
          this.ex = 4;
          this.burst(ecx - 4, ecy, 14, RAMP.cyan, 1.4);
          this.shakeFor(4, 1);
        }
        return true;
      }
      case EV.player_hurt: {
        if (age === 0) {
          this.playerFlash = 4;
          this.playerKnock = 10;
          this.burst(chestX + 2, chestY, 14, RAMP.magenta, 1.3);
        }
        return age > 14;
      }
      case EV.player_healed: {
        if (age === 0) this.burst(chestX, chestY - 6, 10, RAMP.green, 0.8);
        return true;
      }
      case EV.enemy_die: {
        if (age === 0) this.shatterEnemy();
        return true;
      }
    }
    return true;
  }

  private dronePos(k: number): [number, number] {
    return [128 + k * 9, 44 + (k % 2) * 6 + (Math.floor((this.tick + k * 17) / 20) % 2)];
  }

  private pulse() {
    for (let i = 0; i < MAX_PULSES; i++) {
      if (this.pulseAge[i] < 0) {
        this.pulseAge[i] = 0;
        return;
      }
    }
  }

  private spawn(x: number, y: number, vx: number, vy: number, life: number, ramp: number, size = 1, grav = 0, color = -1) {
    const i = this.pnext;
    this.pnext = (i + 1) % MAX_PARTICLES;
    this.px[i] = x;
    this.py[i] = y;
    this.pvx[i] = vx;
    this.pvy[i] = vy;
    this.pg[i] = grav;
    this.plife[i] = life;
    this.pmax[i] = life;
    this.pramp[i] = ramp;
    this.pcolor[i] = color;
    this.psize[i] = size;
  }

  private burst(x: number, y: number, n: number, ramp: number, speed: number) {
    const t = this.tick;
    for (let k = 0; k < n; k++) {
      const a = hash(t * 31 + k * 7) * Math.PI * 2;
      const s = speed * (0.4 + hash(t * 17 + k * 3) * 0.8);
      this.spawn(x, y, Math.cos(a) * s, Math.sin(a) * s, 14 + Math.floor(hash(k * 11 + t) * 14), ramp, k % 5 === 0 ? 2 : 1, 0.03);
    }
  }

  private fire(x0: number, y0: number, x1: number, y1: number, dur: number, ramp: number, size: number, arc: number, burst: number, card = false) {
    for (let i = 0; i < MAX_PROJECTILES; i++) {
      if (this.jlive[i]) continue;
      this.jx0[i] = x0;
      this.jy0[i] = y0;
      this.jx1[i] = x1;
      this.jy1[i] = y1;
      this.jage[i] = 0;
      this.jdur[i] = dur;
      this.jramp[i] = ramp;
      this.jsize[i] = size;
      this.jarc[i] = arc;
      this.jburst[i] = burst;
      this.jcard[i] = card ? 1 : 0;
      this.jlive[i] = 1;
      return;
    }
  }

  private projectilePos(i: number, out: Float32Array) {
    const u = this.jage[i] / this.jdur[i];
    const e = u * u * (3 - 2 * u);
    out[0] = this.jx0[i] + (this.jx1[i] - this.jx0[i]) * e;
    out[1] = this.jy0[i] + (this.jy1[i] - this.jy0[i]) * e - Math.sin(u * Math.PI) * this.jarc[i];
  }

  private tmp = new Float32Array(2);

  private stepProjectiles() {
    for (let i = 0; i < MAX_PROJECTILES; i++) {
      if (!this.jlive[i]) continue;
      this.jage[i]++;
      this.projectilePos(i, this.tmp);
      if (!this.jcard[i]) this.spawn(this.tmp[0], this.tmp[1], 0, 0, 8, this.jramp[i], 1, 0);
      if (this.jage[i] >= this.jdur[i]) {
        this.jlive[i] = 0;
        if (this.jburst[i]) this.burst(this.jx1[i], this.jy1[i], this.jburst[i], this.jramp[i], 1.5);
      }
    }
  }

  private stepParticles() {
    for (let i = 0; i < MAX_PARTICLES; i++) {
      if (this.plife[i] <= 0) continue;
      this.plife[i]--;
      this.px[i] += this.pvx[i];
      this.py[i] += this.pvy[i];
      this.pvy[i] += this.pg[i];
      this.pvx[i] *= 0.96;
      this.pvy[i] *= 0.96;
    }
  }

  private shatterEnemy() {
    const e = this.enemy;
    if (!e || this.enemyDead) return;
    this.enemyDead = true;
    this.flash = 2;
    this.shakeFor(10, 2);
    const ox = ENEMY_X - Math.floor(e.w / 2);
    const oy = FLOOR - e.h;
    const [cx, cy] = this.enemyCenter();
    let n = 0;
    for (let y = 0; y < e.h; y += 2) {
      for (let x = 0; x < e.w; x += 2) {
        const p = e.pixels[y * e.w + x];
        if (!p) continue;
        const dx = ox + x - cx;
        const dy = oy + y - cy;
        const k = n++;
        this.spawn(ox + x, oy + y, dx * 0.05 + (hash(k) - 0.5) * 0.6, -0.3 - hash(k * 3) * 0.9 + dy * 0.02, 40 + Math.floor(hash(k * 7) * 40), RAMP.cyan, 2, 0.01, p - 1);
      }
    }
  }

  // ----------------------------------------------------------------- draw

  private rect(x: number, y: number, w: number, h: number, c: number) {
    this.ctx.fillStyle = COLORS[c];
    this.ctx.fillRect(Math.round(x), Math.round(y), w, h);
  }

  // a 50% checkerboard in one palette color - the only "transparency" there is
  private dither(x: number, y: number, w: number, h: number, c: number) {
    let p = this.patterns[c];
    if (p === undefined) {
      const tile = newCanvas(2, 2);
      const tctx = tile.getContext("2d");
      if (tctx) {
        tctx.fillStyle = COLORS[c];
        tctx.fillRect(0, 0, 1, 1);
        tctx.fillRect(1, 1, 1, 1);
      }
      p = this.ctx.createPattern(tile, "repeat");
      this.patterns[c] = p;
    }
    if (!p) return;
    this.ctx.fillStyle = p;
    this.ctx.fillRect(Math.round(x), Math.round(y), w, h);
  }

  draw() {
    const ctx = this.ctx;
    const t = this.tick;
    ctx.drawImage(this.bg, 0, 0);
    this.drawAmbient(t);
    if (this.tower > 0.05) this.drawTower();
    if (this.enemy && !this.enemyDead) this.drawEnemy(t);
    if (this.playerVisible) this.drawPlayer();
    if (this.wall > 0.05) this.drawWall(t);
    this.drawDrones(t);
    this.drawActionsFront();
    this.drawProjectiles();
    this.drawParticles();
    if (this.sweep >= 0) {
      this.dither(0, HEIGHT - this.sweep, WIDTH, 3, C.cyanHi);
      this.rect(0, HEIGHT - this.sweep + 3, WIDTH, 1, C.white);
    }
    if (this.flash > 0) this.dither(0, 0, WIDTH, HEIGHT, C.white);
    if (this.night) {
      this.dither(0, 0, WIDTH, HEIGHT, C.ink);
      this.dither(1, 0, WIDTH, HEIGHT, C.deepNight);
    }
  }

  private drawAmbient(t: number) {
    const frame = Math.floor(t / 5);

    // twinkling stars
    for (let i = 0; i < this.stars.length; i += 2) {
      const tw = hash(i * 31 + Math.floor(t / 20));
      if (tw < 0.3) continue;
      this.rect(this.stars[i], this.stars[i + 1], 1, 1, tw > 0.85 ? C.white : tw > 0.6 ? C.lavender : C.violetLight);
    }

    // rack LEDs: cyan bars flicker, red lamps blink
    for (let r = 0; r < 7; r++) {
      const x = 126 + r * 16;
      const h = 22 + Math.round(hash(r * 5 + 3) * 16);
      const top = FLOOR - h;
      if (hash(r * 13 + Math.floor(t / 12)) > 0.4) this.rect(x + 6, top + 2, 1, 1, C.red);
      const ly = top + 5 + Math.floor(hash(r + frame * 7) * (h - 8));
      this.rect(x + 3, ly, 1, 2, C.cyanHi);
    }

    // floating voxels
    for (let k = 0; k < 7; k++) {
      const vx = 132 + Math.round(hash(k * 3) * 100);
      const vy = 20 + Math.round(hash(k * 9) * 50) + (Math.floor((t + k * 23) / 24) % 2);
      this.rect(vx, vy, 2, 2, k % 3 === 0 ? C.cyanMid : C.cyan);
      this.rect(vx, vy, 1, 1, C.cyanHi);
    }

    // the rift: a jagged white seam, amber on the lab side, cyan on the other
    // (it only tears open after the night of the intro)
    const flare = this.riftFlare > 0 ? 1 : 0;
    for (let y = 0; y < (this.night ? 0 : HEIGHT); y++) {
      // the monitor hangs in front of it
      if (y >= MONITOR.y - 3 && y < MONITOR.y + MONITOR.h + 3) continue;
      const seg = Math.floor(y / 3);
      const o = Math.round((hash(seg * 7 + frame * 13) - 0.5) * 4);
      const x = RIFT_X + o;
      this.rect(x - 2 - flare, y, 1, 1, C.amber);
      this.rect(x - 1, y, 1, 1, C.amberHi);
      this.rect(x, y, 1, 1, C.white);
      this.rect(x + 1, y, 1, 1, C.cyanHi);
      this.rect(x + 2 + flare, y, 1, 1, C.cyan);
      if ((y + frame) % 3 === 0) {
        this.rect(x - 4 - flare * 2, y, 1, 1, C.amberDark);
        this.rect(x + 4 + flare * 2, y, 1, 1, C.cyanMid);
      }
    }

    // the Tesla coil's crown sparks
    if (!this.night) {
      const surge = this.coilSurge > 0 || this.status.amplifiers > 0;
      if (surge || hash(frame * 3) > 0.55) {
        let x = 16;
        let y = 36;
        const dir = hash(frame) < 0.5 ? -1 : 1;
        const c = surge ? C.magentaHi : C.amberHi;
        for (let k = 0; k < 8; k++) {
          x += dir;
          y += Math.round((hash(frame * 11 + k) - 0.6) * 3);
          this.rect(x, y, 1, 1, k < 2 ? C.white : c);
        }
      }
      // the lamp's bulb flickers now and then
      this.rect(PLAYER_X - 1, 17, 3, 1, hash(Math.floor(t / 7)) > 0.05 ? C.amberHi : C.amber);
    } else {
      this.rect(PLAYER_X - 1, 17, 3, 1, C.wood2);
    }

    // monitor LEDs
    for (let k = 0; k < 5; k++) {
      const on = hash(k * 19 + Math.floor(t / 15)) > 0.35;
      this.rect(MONITOR.x + MONITOR.w + 1, MONITOR.y + 3 + k * 6, 1, 2, on ? (k % 2 ? C.cyanHi : C.red) : C.iron);
    }

    // the keys light under his fingers
    const k = KEYBOARD;
    for (let i = 0; i < k.w - 2; i += 2) {
      const lit = this.keysLit > 0 && hash(i + frame * 5) > 0.45;
      this.rect(k.x + 1 + i, k.y, 1, 1, lit ? C.cyanHi : C.cyanMid);
    }

    // a signal crawling down the cable into the rift
    for (let i = 0; i < MAX_PULSES; i++) {
      const a = this.pulseAge[i];
      if (a < 0) continue;
      for (let s = 0; s < 4; s++) {
        const p = CABLE[Math.min(CABLE.length - 1, Math.max(0, a - s))];
        this.rect(p[0], p[1], 1, 1, s === 0 ? C.white : s === 1 ? C.cyanHi : C.cyan);
      }
    }
  }

  private drawEnemy(t: number) {
    const e = this.enemy;
    const img = this.enemyCanvas;
    const flashImg = this.enemyFlashCanvas;
    if (!e || !img || !flashImg) return;
    const hover = Math.floor(t / 20) % 2;
    const x = ENEMY_X - Math.floor(e.w / 2) + Math.round(this.ex);
    let y = FLOOR - e.h - hover;
    if (this.enemyAppear > 0) y += Math.round(this.enemyAppear / 3);

    // contact shadow
    const [, cy] = this.enemyCenter();
    const sw = Math.round((FLOOR - cy) * 1.4) + 6;
    this.dither(ENEMY_X - Math.floor(sw / 2), FLOOR, sw, 2, C.ink);

    const ctx = this.ctx;
    if (this.enemyFlash > 0) {
      ctx.drawImage(flashImg, x, y);
    } else if (this.glitch > 0) {
      // sliced sideways like a corrupted frame
      for (let row = 0; row < e.h; row += 3) {
        const off = Math.round((hash(row * 7 + t) - 0.5) * 5);
        ctx.drawImage(img, 0, row, e.w, 3, x + off, y + row, e.w, 3);
      }
    } else {
      ctx.drawImage(img, x, y);
    }

    // blink
    if (t % 190 < 7 && this.enemyFlash === 0) {
      for (const eye of e.eyes) {
        // lids down: the socket takes the skin color, a dark lash line across
        this.rect(x + eye.x - 1, y + eye.y - 1, eye.s + 2, eye.s + 2, e.body[1]);
        this.rect(x + eye.x - 1, y + eye.y + Math.floor(eye.s / 2), eye.s + 2, 1, C.ink);
      }
    }

    // bracing: a steel hex shield in front of it
    if (this.enemyShield > 0.05) {
      const h = Math.round(34 * Math.min(1, this.enemyShield));
      const sx = ENEMY_X - Math.floor(e.w / 2) + 6;
      const top = FLOOR - h;
      if (hash(Math.floor(t / 4)) > 0.3) this.dither(sx - 2, top, 6, h, C.lavender);
      for (let yy = 0; yy < h; yy += 5) {
        const shift = (yy / 5) % 2 ? 2 : 0;
        this.rect(sx - 1 + shift, top + yy, 4, 4, C.ink);
        this.rect(sx + shift, top + yy + 1, 2, 2, C.steel);
        this.rect(sx + shift, top + yy + 1, 1, 1, C.white);
      }
      this.rect(sx - 2, top, 1, h, C.white);
    }
  }

  private drawWall(t: number) {
    // the firewall: amber bricks between him and the rift
    const h = Math.round(36 * Math.min(1, this.wall));
    const x = 88;
    const top = FLOOR - h;
    for (let row = 0; row * 3 < h; row++) {
      const y = FLOOR - (row + 1) * 3;
      const off = row % 2 ? 2 : 0;
      for (let bx = -off; bx < 6; bx += 4) {
        const x0 = Math.max(x, x + bx);
        const w = Math.min(x + 6, x + bx + 3) - x0;
        if (w <= 0) continue;
        const hot = hash(row * 5 + bx + Math.floor(t / 6)) > 0.8;
        this.rect(x0, y, w, 2, hot ? C.amberHi : C.amber);
        this.rect(x0, y + 2, w, 1, C.amberDark);
      }
    }
    this.dither(x - 1, top, 1, h, C.cyan);
    this.dither(x + 6, top + 1, 1, h - 1, C.amberHi);
  }

  private drawTower() {
    // Mainframe: steel slabs stacked behind him
    const n = Math.round(3 * Math.min(1, this.tower));
    for (let k = 0; k < n; k++) {
      const y = FLOOR - (k + 1) * 7;
      this.rect(34, y, 11, 7, C.ink);
      this.rect(35, y + 1, 9, 5, C.iron);
      this.rect(35, y + 1, 9, 1, C.steel);
      this.rect(37, y + 3, 1, 1, (this.tick + k * 9) % 40 < 20 ? C.cyanHi : C.cyanMid);
      this.rect(39, y + 3, 4, 1, C.cyanDark);
    }
  }

  private drawDrones(t: number) {
    const n = Math.round(this.drones);
    for (let k = 0; k < n; k++) {
      const [x, y] = this.dronePos(k);
      this.rect(x - 1, y - 1, 7, 5, C.ink);
      this.rect(x, y, 5, 3, C.steel);
      this.rect(x, y, 5, 1, C.white);
      this.rect(x + 3, y + 1, 1, 1, (t + k * 11) % 30 < 20 ? C.red : C.redDark);
      // rotor
      const r = Math.floor(t / 3) % 2;
      this.rect(x - 1 + r, y - 2, 3, 1, C.steel);
      this.rect(x + 3 - r, y - 2, 3, 1, C.iron);
    }
  }

  private drawActionsFront() {
    for (let i = 0; i < MAX_ACTIONS; i++) {
      const kind = this.akind[i];
      const age = this.aage[i];
      if (age < 0) continue;
      if (kind === EV.final_strike && age >= 26 && age < 36) {
        // the Kernel Panic beam: white core, red glow, flickering
        const x0 = PLAYER_X + 22;
        const [ex, ey] = this.enemyCenter();
        const y0 = FLOOR - 28;
        const w = age < 30 ? 3 : 1;
        for (let x = x0; x < ex; x++) {
          const y = Math.round(y0 + ((ey - y0) * (x - x0)) / (ex - x0));
          const j = hash(x + age * 31) > 0.85 ? 1 : 0;
          this.rect(x, y - w - j, 1, 1, C.red);
          this.rect(x, y - Math.floor(w / 2), 1, w, C.white);
          this.rect(x, y + w - Math.floor(w / 2) + j, 1, 1, C.redDark);
        }
      }
      if ((kind === EV.attack || kind === EV.damage_boost) && age >= HIT_AT && age < HIT_AT + 6) {
        // the exploit cuts through: a diagonal slash across the enemy
        const [ex, ey] = this.enemyCenter();
        const len = 12 - (age - HIT_AT);
        for (let k = -len; k <= len; k++) {
          this.rect(ex + k, ey - Math.round(k * 0.7), 1, 1, Math.abs(k) < len / 2 ? C.white : C.cyanHi);
          this.rect(ex + k, ey - Math.round(k * 0.7) + 1, 1, 1, C.cyan);
        }
      }
      if (kind === EV.armor && age >= 28 && age < 44 && age % 4 < 3) {
        // a padlock snaps shut on his chest
        const x = PLAYER_X - 1;
        const y = FLOOR - 22;
        this.rect(x - 1, y - 4, 6, 9, C.ink);
        this.rect(x, y - 3, 4, 1, C.cyanHi);
        this.rect(x, y - 3, 1, 3, C.cyanHi);
        this.rect(x + 3, y - 3, 1, 3, C.cyanHi);
        this.rect(x - 1 + 1, y, 4, 4, C.cyan);
        this.rect(x + 1, y + 1, 2, 2, C.ink);
      }
      if ((kind === EV.retrieve || kind === EV.restore || kind === EV.reboot) && age < 36) {
        // a clock face turning backwards around him
        const cx = PLAYER_X + 1;
        const cy = FLOOR - 20;
        for (let k = 0; k < 12; k++) {
          const a = (k / 12) * Math.PI * 2;
          this.rect(cx + Math.round(Math.cos(a) * 18), cy + Math.round(Math.sin(a) * 20), 1, 1, k % 3 === 0 ? C.lavender : C.violetLight);
        }
        const hand = -age * 0.35;
        for (let r = 2; r < 15; r++) this.rect(cx + Math.round(Math.cos(hand) * r), cy + Math.round(Math.sin(hand) * r), 1, 1, C.lavender);
      }
    }
  }

  private drawProjectiles() {
    for (let i = 0; i < MAX_PROJECTILES; i++) {
      if (!this.jlive[i]) continue;
      this.projectilePos(i, this.tmp);
      const x = Math.round(this.tmp[0]);
      const y = Math.round(this.tmp[1]);
      const ramp = RAMPS[this.jramp[i]];
      if (this.jcard[i]) {
        this.rect(x - 1, y - 2, 4, 5, C.ink);
        this.rect(x, y - 1, 2, 3, C.white);
        this.rect(x, y + 1, 2, 1, C.cyan);
        continue;
      }
      const s = this.jsize[i];
      this.rect(x - s, y - s, s * 2 + 1, s * 2 + 1, ramp[2]);
      this.rect(x - s + 1, y - s + 1, s * 2 - 1, s * 2 - 1, ramp[1]);
      this.rect(x, y, 1, 1, C.white);
    }
  }

  private drawParticles() {
    for (let i = 0; i < MAX_PARTICLES; i++) {
      const life = this.plife[i];
      if (life <= 0) continue;
      let c = this.pcolor[i];
      if (c < 0) {
        const ramp = RAMPS[this.pramp[i]];
        c = ramp[Math.min(ramp.length - 1, Math.floor((1 - life / this.pmax[i]) * ramp.length))];
      } else if (life < 10) {
        c = life % 2 ? c : C.cyanHi;
      }
      const size = this.psize[i];
      if (size === 3) {
        // a "+" glyph
        this.rect(this.px[i] - 1, this.py[i], 3, 1, c);
        this.rect(this.px[i], this.py[i] - 1, 1, 3, c);
      } else {
        this.rect(this.px[i], this.py[i], size, size, c);
      }
    }
  }

  // --- Dr. Chronos, ~22 x 40 logical pixels, built from rects each frame.
  // Pass 0 draws every part grown by one pixel in the outline color, pass 1
  // fills: the union gets a clean 1px outline, inner edges are left to the
  // shading.
  private pass = 0;
  private ox = 0;
  private oy = 0;
  private flashDraw = false;

  private part(x: number, y: number, w: number, h: number, c: number) {
    if (this.pass === 0) this.rect(this.ox + x - 1, this.oy + y - 1, w + 2, h + 2, this.outlineColor());
    else this.rect(this.ox + x, this.oy + y, w, h, this.flashDraw ? C.white : c);
  }

  private outlineColor(): number {
    return this.status.armor > 0 && this.tick % 40 < 30 ? C.cyanDark : C.ink;
  }

  // a 2px-thick limb from (x0,y0) to (x1,y1), relative to the origin
  private limb(x0: number, y0: number, x1: number, y1: number, c: number) {
    const n = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
    for (let k = 0; k <= n; k++) {
      const x = Math.round(x0 + ((x1 - x0) * k) / n);
      const y = Math.round(y0 + ((y1 - y0) * k) / n);
      this.part(x, y, 2, 2, c);
    }
  }

  private drawPlayer() {
    const s = this.shown;
    const knock = this.playerKnock > 0 ? -Math.ceil(this.playerKnock / 4) : 0;
    this.flashDraw = this.playerFlash > 0 && this.playerFlash % 2 === 0;

    // contact shadow
    this.dither(PLAYER_X - 9 + knock, FLOOR, 18, 2, C.ink);

    for (this.pass = 0; this.pass < 2; this.pass++) {
      // legs and boots stay planted
      this.ox = PLAYER_X + knock;
      this.oy = FLOOR;
      this.part(-4, -8, 3, 6, C.cloth0);
      this.part(1, -8, 3, 6, C.cloth1);
      this.part(-5, -2, 5, 2, C.wood1);
      this.part(1, -2, 6, 2, C.wood1);

      // everything above the hips breathes and leans
      this.ox = PLAYER_X + knock + s.lean;
      this.oy = FLOOR + s.bob;

      // copper pack with its coil and glowing ball
      this.part(-10, -23, 4, 11, C.amberDark);
      this.part(-9, -30, 2, 7, C.brassDark);
      this.part(-10, -33, 4, 3, C.amber);

      // back arm, behind the coat
      this.limb(-2, -22, s.bx - 1, s.by, C.coatShade);
      this.part(s.bx - 1, s.by, 2, 2, C.redDark);

      // coat
      this.part(-6, -24, 12, 17, C.coat);
      this.part(-7, -10, 14, 3, C.coat);

      // head, hair
      const hx = s.tilt;
      this.part(-4 + hx, -34, 9, 9, C.skin);
      this.part(5 + hx, -30, 2, 2, C.skin);
      this.hair(hx);

      // front arm with what it holds
      this.limb(3, -22, s.fx, s.fy, C.coat);
      this.part(s.fx, s.fy, 2, 2, C.red);
      if (this.item === 1) this.part(s.fx + 1, s.fy - 4, 3, 4, C.green);
      if (this.item === 2) this.part(s.fx + 1, s.fy - 1, 6, 2, C.brass);
    }
    this.pass = 1;
    if (this.flashDraw) return;

    // shading and details, drawn over the fills
    const ox = PLAYER_X + knock + s.lean;
    const oy = FLOOR + s.bob;
    const L = PLAYER_X + knock;
    this.rect(L + 3, FLOOR - 2, 4, 1, C.wood2);
    this.rect(L - 4, FLOOR - 8, 1, 6, C.ink);
    // pack
    this.rect(ox - 8, oy - 22, 1, 9, C.amber);
    for (let k = 0; k < 3; k++) this.rect(ox - 9, oy - 29 + k * 2, 2, 1, C.brass);
    const ball = this.coilSurge > 0 || this.status.amplifiers > 0 ? C.magentaHi : C.amberHi;
    this.rect(ox - 9, oy - 33, 2, 2, ball);
    // coat shading, vest, buttons, hem
    this.rect(ox - 6, oy - 24, 2, 17, C.coatShade);
    this.rect(ox - 7, oy - 10, 2, 3, C.coatShade);
    this.rect(ox + 1, oy - 24, 3, 12, C.cloth1);
    this.rect(ox + 2, oy - 22, 1, 1, C.brass);
    this.rect(ox + 2, oy - 19, 1, 1, C.brass);
    this.rect(ox + 2, oy - 16, 1, 1, C.brass);
    this.rect(ox - 3, oy - 14, 3, 1, C.coatShade);
    this.rect(ox - 7, oy - 8, 14, 1, C.coatShade);
    // bow tie
    this.rect(ox + 1, oy - 25, 3, 2, C.red);
    this.rect(ox + 2, oy - 25, 1, 2, C.redDark);
    // face
    const hx = ox + s.tilt;
    this.rect(hx - 4, oy - 33, 1, 7, C.skinShade);
    this.rect(hx + 3, oy - 33, 1, 2, C.skinHi);
    this.rect(hx - 1, oy - 30, 1, 2, C.skinShade);
    this.rect(hx + 5, oy - 29, 2, 1, C.skinShade);
    // goggles: strap and a glowing lens
    this.rect(hx - 4, oy - 31, 9, 1, C.cloth0);
    this.rect(hx + 1, oy - 32, 3, 3, C.brass);
    const lens = this.rim > 0.5 ? C.white : C.amberHi;
    this.rect(hx + 2, oy - 31, 1, 1, lens);
    this.rect(hx + 4, oy - 32, 1, 2, C.brassDark);
    // moustache
    this.rect(hx + 2, oy - 28, 5, 1, C.white);
    this.rect(hx + 1, oy - 27, 3, 1, C.coat);
    this.rect(hx + 5, oy - 27, 2, 1, C.coat);
    // front sleeve shading
    this.rect(ox + 3, oy - 21, 1, 1, C.coatShade);
    // held items
    if (this.item === 1) {
      this.rect(ox + s.fx + 2, oy + s.fy - 3, 1, 1, C.greenHi);
      this.rect(ox + s.fx + 2, oy + s.fy - 5, 1, 1, C.wood4);
    }
    if (this.item === 2) {
      this.rect(ox + s.fx + 1, oy + s.fy - 1, 6, 1, C.brassHi);
      this.rect(ox + s.fx + 7, oy + s.fy - 1, 1, 2, this.tick % 4 < 2 ? C.white : C.red);
    }

    // rim light from whatever he is channelling, on his rift-facing edge
    if (this.rim > 0.15) {
      const c = this.rim > 0.6 ? this.rimColor : C.cyanMid;
      this.rect(ox + 6, oy - 24, 1, 14, c);
      this.rect(hx + 5, oy - 34, 1, 4, c);
      this.rect(hx + 1, oy - 35, 3, 1, c);
    }
  }

  private hair(hx: number) {
    // a white shock of hair off the back and top of his head, tips swaying
    const sway = Math.floor(this.tick / 12) % 2;
    const tufts: [number, number, number, number][] = [
      [-6, -36, 5, 8],
      [-5, -38, 7, 3],
      [-8, -34, 3, 3],
      [-9, -31, 3, 2],
      [-3, -40, 2, 3],
      [0, -39, 2, 2],
      [2, -37, 2, 2],
      [-7, -37, 2, 2],
      [-10, -35, 2, 1],
    ];
    for (let i = 0; i < tufts.length; i++) {
      const [x, y, w, h] = tufts[i];
      const dx = i > 3 && i % 2 === sway ? -1 : 0;
      this.part(x + hx + dx, y, w, h, i < 2 ? C.coat : C.white);
    }
  }

  // --------------------------------------------------------- static layers

  private spriteCanvas(sprite: EnemySprite, flash: boolean): HTMLCanvasElement {
    const c = newCanvas(sprite.w, sprite.h);
    const ctx = c.getContext("2d");
    if (!ctx) return c;
    for (let y = 0; y < sprite.h; y++) {
      for (let x = 0; x < sprite.w; x++) {
        const p = sprite.pixels[y * sprite.w + x];
        if (!p) continue;
        ctx.fillStyle = COLORS[flash ? (p - 1 === C.ink ? C.ink : C.white) : p - 1];
        ctx.fillRect(x, y, 1, 1);
      }
    }
    return c;
  }

  private paintBackground(): HTMLCanvasElement {
    const canvas = newCanvas(WIDTH, HEIGHT);
    const ctx = canvas.getContext("2d");
    if (!ctx) return canvas;
    const r = (x: number, y: number, w: number, h: number, c: number) => {
      ctx.fillStyle = COLORS[c];
      ctx.fillRect(x, y, w, h);
    };
    const d = (x: number, y: number, w: number, h: number, c: number) => {
      ctx.fillStyle = COLORS[c];
      for (let yy = y; yy < y + h; yy++) for (let xx = x + ((x + yy) % 2); xx < x + w; xx += 2) ctx.fillRect(xx, yy, 1, 1);
    };

    // ----- the lab
    // wall: vertical planks
    for (let x = 0; x < RIFT_X; x += 6) {
      r(x, 0, 6, FLOOR, (x / 6) % 2 ? C.wood1 : C.wood2);
      r(x, 0, 1, FLOOR, C.wood0);
      for (let k = 0; k < 4; k++) r(x + 2 + (k % 3), 8 + Math.floor(hash(x * 3 + k) * 70), 1, 3, C.wood0);
    }
    // wainscot rail
    r(0, 60, RIFT_X, 1, C.wood4);
    r(0, 61, RIFT_X, 2, C.wood3);
    r(0, 63, RIFT_X, 1, C.wood0);
    for (let x = 0; x < RIFT_X; x += 6) r(x, 64, 6, FLOOR - 64, (x / 6) % 2 ? C.wood0 : C.wood1);
    // warm light pooling under the lamp
    d(PLAYER_X - 14, 20, 28, 40, C.wood3);
    d(PLAYER_X - 20, 40, 40, 20, C.wood2);
    // lamp
    r(PLAYER_X, 0, 1, 14, C.ink);
    r(PLAYER_X - 4, 14, 9, 1, C.ink);
    r(PLAYER_X - 3, 13, 7, 1, C.brassDark);
    r(PLAYER_X - 4, 14, 9, 2, C.brass);
    r(PLAYER_X - 5, 16, 11, 1, C.brassDark);
    // copper pipes along the ceiling, one coming down
    r(0, 3, RIFT_X - 4, 3, C.amberDark);
    r(0, 3, RIFT_X - 4, 1, C.amber);
    r(0, 6, RIFT_X - 4, 1, C.ink);
    r(0, 9, RIFT_X - 8, 2, C.brassDark);
    r(0, 9, RIFT_X - 8, 1, C.brass);
    r(104, 6, 3, FLOOR - 6, C.amberDark);
    r(104, 6, 1, FLOOR - 6, C.amber);
    r(107, 6, 1, FLOOR - 6, C.ink);
    for (let y = 16; y < FLOOR; y += 18) r(103, y, 5, 2, C.brass);
    // shelves with jars and books
    r(24, 34, 26, 2, C.wood4);
    r(24, 36, 26, 1, C.wood0);
    const jars = [C.green, C.amber, C.magenta, C.cyan, C.amberHi, C.green];
    for (let k = 0; k < jars.length; k++) {
      const x = 26 + k * 4;
      const h = 3 + (k % 3);
      r(x - 1, 34 - h - 1, 4, h + 1, C.ink);
      r(x, 34 - h, 2, h, jars[k]);
      r(x, 34 - h, 1, 1, C.white);
    }
    r(24, 48, 26, 2, C.wood4);
    r(24, 50, 26, 1, C.wood0);
    const books = [C.redDark, C.cyanDark, C.brassDark, C.cloth2, C.greenDark, C.magentaDark, C.redDark];
    for (let k = 0; k < books.length; k++) {
      const h = 6 + (k % 3);
      r(26 + k * 3, 48 - h, 2, h, books[k]);
      r(26 + k * 3, 48 - h, 2, 1, C.wood4);
    }
    // the Tesla coil
    r(6, FLOOR - 8, 16, 8, C.ink);
    r(7, FLOOR - 7, 14, 7, C.iron);
    r(7, FLOOR - 7, 14, 1, C.steel);
    for (let y = 44; y < FLOOR - 8; y += 2) {
      r(11, y, 8, 2, C.ink);
      r(12, y, 6, 1, C.brass);
      r(12, y + 1, 6, 1, C.amberDark);
    }
    r(8, 40, 14, 4, C.ink);
    r(9, 41, 12, 2, C.brass);
    r(9, 41, 12, 1, C.brassHi);
    r(12, 34, 7, 6, C.ink);
    r(13, 35, 5, 4, C.steel);
    r(13, 35, 2, 1, C.white);
    // chalkboard between the pult and the rift
    r(84, 44, 26, 16, C.wood3);
    r(85, 45, 24, 14, C.ink);
    r(86, 46, 22, 12, C.greenDark);
    d(86, 46, 22, 12, C.ink);
    const chalk = [
      [88, 48, 7],
      [96, 48, 5],
      [88, 51, 11],
      [89, 54, 6],
      [97, 54, 8],
      [100, 51, 5],
    ];
    for (const [x, y, w] of chalk) r(x, y, w, 1, C.coat);
    r(84, 60, 26, 1, C.wood4);

    // ----- the pult, keyboard and cable
    const k = KEYBOARD;
    r(k.x + 5, k.y + 3, 3, FLOOR - k.y - 3, C.ink);
    r(k.x + 6, k.y + 3, 1, FLOOR - k.y - 3, C.steel);
    r(k.x + 2, FLOOR - 2, 9, 2, C.ink);
    r(k.x + 3, FLOOR - 2, 7, 1, C.iron);
    r(k.x - 1, k.y - 1, k.w + 2, 4, C.ink);
    r(k.x, k.y, k.w, 2, C.cloth2);
    r(k.x, k.y + 1, k.w, 1, C.iron);
    for (const [x, y] of CABLE) {
      r(x, y, 1, 1, C.ink);
      r(x, y - 1, 1, 1, C.cloth1);
    }
    for (let i = 8; i < CABLE.length; i += 7) r(CABLE[i][0], CABLE[i][1] - 1, 1, 1, C.cyanDark);

    // lab floor: boards running into the room
    r(0, FLOOR, RIFT_X, HEIGHT - FLOOR, C.wood1);
    r(0, FLOOR, RIFT_X, 1, C.wood4);
    for (let y = FLOOR + 2, gap = 2; y < HEIGHT; y += gap, gap++) r(0, y, RIFT_X, 1, C.wood0);
    for (let x = 4; x < RIFT_X; x += 13) r(x, FLOOR + 1, 1, HEIGHT - FLOOR, C.wood0);

    // ----- the machine world
    const X = RIFT_X + 1;
    const W = WIDTH - X;
    r(X, 0, W, FLOOR, C.deepNight);
    d(X, 18, W, 6, C.night);
    r(X, 24, W, 30, C.night);
    d(X, 54, W, 6, C.violet);
    r(X, 60, W, FLOOR - 60, C.violet);
    d(X, FLOOR - 8, W, 8, C.violetLight);
    // far towers
    for (let x = X + 2; x < WIDTH; x += 9) {
      const h = 18 + Math.round(hash(x) * 30);
      r(x, FLOOR - h, 6, h, C.deepNight);
      for (let w = 0; w < 4; w++) r(x + 1 + (w % 2) * 3, FLOOR - h + 3 + w * 5, 1, 1, C.cyanDark);
    }
    // server racks
    for (let i = 0; i < 7; i++) {
      const x = 126 + i * 16;
      const h = 22 + Math.round(hash(i * 5 + 3) * 16);
      const top = FLOOR - h;
      r(x - 1, top - 1, 10, h + 1, C.ink);
      r(x, top, 8, h, C.cloth0);
      r(x, top, 8, 1, C.violetLight);
      r(x + 7, top + 1, 1, h - 1, C.night);
      r(x + 2, top + 4, 1, h - 6, C.cyanMid);
      r(x + 5, top + 4, 1, h - 6, C.cyanDark);
    }
    // the grid floor, converging on a point behind the enemy
    r(X, FLOOR, W, HEIGHT - FLOOR, C.ink);
    for (let y = FLOOR, gap = 1; y < HEIGHT; y += gap, gap++) r(X, y, W, 1, y === FLOOR ? C.cyanMid : C.cyanDark);
    const vx = ENEMY_X;
    const vy = FLOOR - 16;
    for (let bx = X - 60; bx < WIDTH + 60; bx += 12) {
      for (let y = FLOOR; y < HEIGHT; y++) {
        const x = Math.round(vx + ((bx - vx) * (y - vy)) / (HEIGHT - vy));
        if (x > X && x < WIDTH) r(x, y, 1, 1, C.cyanDark);
      }
    }

    // ----- the monitor over the rift
    const M = MONITOR;
    r(M.x + 12, 0, 1, M.y - 2, C.ink);
    r(M.x + M.w - 13, 0, 1, M.y - 2, C.ink);
    r(M.x - 3, M.y - 3, M.w + 6, M.h + 6, C.ink);
    r(M.x - 2, M.y - 2, M.w / 2 + 2, M.h + 4, C.brassDark);
    r(M.x - 2, M.y - 2, M.w / 2 + 2, 1, C.brass);
    r(M.x + M.w / 2, M.y - 2, M.w / 2 + 2, M.h + 4, C.iron);
    r(M.x + M.w / 2, M.y - 2, M.w / 2 + 2, 1, C.cyan);
    r(M.x + M.w + 1, M.y - 2, 1, M.h + 4, C.cyanMid);
    for (let k2 = 0; k2 < 5; k2++) r(M.x - 2, M.y + 3 + k2 * 6, 1, 2, C.amber);
    r(M.x, M.y, M.w, M.h, C.deepNight);
    for (let y = M.y + 1; y < M.y + M.h; y += 2) r(M.x, y, M.w, 1, C.ink);

    return canvas;
  }
}

