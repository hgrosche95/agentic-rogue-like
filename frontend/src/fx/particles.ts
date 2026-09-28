import { reducedMotion, type Point } from "./motion";

// One fixed, full-viewport canvas for every particle - pixels knocked out of
// a hit, drones of a Botnet, green code of a heal. It spans the whole page
// because many effects travel between the arena and the table below it
// (field slots, piles). The loop only runs while particles are alive.

export interface ParticleSpec {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  // acceleration, px/s² (gravity is a positive ay)
  ay?: number;
  // velocity kept per second, 1 = no drag
  drag?: number;
  ttl: number; // ms
  delay?: number; // ms before it appears
  size?: number;
  color: string;
  // draws a character/word instead of a square
  glyph?: string;
  spin?: number; // deg/s
  // flies along a curve to `to` (through `via`) instead of moving freely,
  // calling `onArrive` once it gets there
  to?: Point;
  via?: Point;
  onArrive?: () => void;
  glow?: boolean;
}

interface Particle extends Required<Omit<ParticleSpec, "glyph" | "to" | "via" | "onArrive">> {
  glyph?: string;
  to?: Point;
  via?: Point;
  onArrive?: () => void;
  age: number;
  rot: number;
  x0: number;
  y0: number;
}

let canvas: HTMLCanvasElement | null = null;
let ctx: CanvasRenderingContext2D | null = null;
let particles: Particle[] = [];
let frame = 0;
let last = 0;

function ensureCanvas(): CanvasRenderingContext2D | null {
  if (canvas && ctx && canvas.isConnected) return ctx;
  canvas = document.createElement("canvas");
  canvas.className = "fx-canvas";
  canvas.setAttribute("aria-hidden", "true");
  document.body.appendChild(canvas);
  ctx = canvas.getContext("2d");
  resize();
  window.addEventListener("resize", resize);
  return ctx;
}

function resize() {
  if (!canvas) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(window.innerWidth * dpr);
  canvas.height = Math.round(window.innerHeight * dpr);
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
}

export function emit(spec: ParticleSpec): void {
  if (reducedMotion() || !ensureCanvas()) return;
  particles.push({
    vx: 0,
    vy: 0,
    ay: 0,
    drag: 1,
    delay: 0,
    size: 4,
    spin: 0,
    glow: false,
    ...spec,
    age: 0,
    rot: Math.random() * 360,
    x0: spec.x,
    y0: spec.y,
  });
  if (!frame) {
    last = performance.now();
    frame = requestAnimationFrame(tick);
  }
}

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
}

function tick(now: number) {
  const dt = Math.min(50, now - last);
  last = now;
  const c = ctx;
  if (!c || !canvas) {
    frame = 0;
    return;
  }
  c.clearRect(0, 0, window.innerWidth, window.innerHeight);

  const alive: Particle[] = [];
  for (const p of particles) {
    p.age += dt;
    if (p.age < p.delay) {
      alive.push(p);
      continue;
    }
    const t = (p.age - p.delay) / p.ttl;
    if (t >= 1) {
      p.onArrive?.();
      continue;
    }
    if (p.to) {
      // quadratic bezier from the start through `via` to `to`
      const e = easeInOut(t);
      const via = p.via ?? { x: (p.x0 + p.to.x) / 2, y: (p.y0 + p.to.y) / 2 };
      const u = 1 - e;
      p.x = u * u * p.x0 + 2 * u * e * via.x + e * e * p.to.x;
      p.y = u * u * p.y0 + 2 * u * e * via.y + e * e * p.to.y;
    } else {
      const s = dt / 1000;
      const keep = p.drag ** s;
      p.vx *= keep;
      p.vy = p.vy * keep + p.ay * s;
      p.x += p.vx * s;
      p.y += p.vy * s;
    }
    p.rot += p.spin * (dt / 1000);
    alive.push(p);

    c.globalAlpha = p.to ? Math.min(1, (1 - t) * 4) : 1 - t;
    c.fillStyle = p.color;
    c.shadowBlur = p.glow ? 10 : 0;
    c.shadowColor = p.color;
    if (p.glyph) {
      c.font = `600 ${p.size}px "IBM Plex Mono", monospace`;
      c.fillText(p.glyph, p.x, p.y);
    } else {
      c.save();
      c.translate(p.x, p.y);
      c.rotate((p.rot * Math.PI) / 180);
      c.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
      c.restore();
    }
  }
  c.globalAlpha = 1;
  c.shadowBlur = 0;
  particles = alive;
  frame = particles.length ? requestAnimationFrame(tick) : 0;
  if (!frame) c.clearRect(0, 0, window.innerWidth, window.innerHeight);
}

// A radial burst of square "voxels" - what a hit knocks out of its target.
export function burst(
  at: Point,
  { count = 18, colors = ["#8ff2ef", "#4fd8e0", "#1a2e3e"], speed = 260, size = 5, delay = 0, gravity = 380 } = {},
): void {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const v = speed * (0.35 + Math.random() * 0.8);
    emit({
      x: at.x,
      y: at.y,
      vx: Math.cos(angle) * v,
      vy: Math.sin(angle) * v - speed * 0.25,
      ay: gravity,
      drag: 0.2,
      ttl: 500 + Math.random() * 450,
      delay,
      size: size * (0.6 + Math.random() * 0.8),
      color: colors[i % colors.length],
      spin: (Math.random() - 0.5) * 900,
    });
  }
}

// A rectangle (a card, a slot) crumbling into pixels that drift off - or,
// with `to`, stream into a point (the banished pile).
export function disintegrate(
  rect: DOMRect,
  { colors = ["#c08a3a", "#ecdfc0", "#4fd8e0"], count = 60, to, delay = 0 }: { colors?: string[]; count?: number; to?: Point; delay?: number } = {},
): void {
  for (let i = 0; i < count; i++) {
    const x = rect.left + Math.random() * rect.width;
    const y = rect.top + Math.random() * rect.height;
    // dissolve top to bottom, like a scan line eating the card
    const lag = ((y - rect.top) / Math.max(1, rect.height)) * 260;
    const color = colors[i % colors.length];
    if (to) {
      emit({
        x,
        y,
        to,
        via: { x: (x + to.x) / 2 + (Math.random() - 0.5) * 160, y: Math.min(y, to.y) - 60 - Math.random() * 90 },
        ttl: 520 + Math.random() * 380,
        delay: delay + lag,
        size: 3 + Math.random() * 3,
        color,
        glow: i % 4 === 0,
      });
    } else {
      emit({
        x,
        y,
        vx: (Math.random() - 0.5) * 120,
        vy: -40 - Math.random() * 160,
        ay: -60,
        drag: 0.4,
        ttl: 600 + Math.random() * 500,
        delay: delay + lag,
        size: 3 + Math.random() * 4,
        color,
        spin: (Math.random() - 0.5) * 600,
      });
    }
  }
}

const CODE = ["0x1F", "fix()", "{ }", "hp++", "0101", "patch", "ok", "</>", "++", "sudo", "#!", ";"];

// Green code fragments rising around a point - a hotfix being applied.
export function risingCode(at: Point, { spread = 90, count = 22, color = "#8dffa0", delay = 0 } = {}): void {
  for (let i = 0; i < count; i++) {
    emit({
      x: at.x + (Math.random() - 0.5) * spread * 2,
      y: at.y + Math.random() * spread,
      vy: -70 - Math.random() * 90,
      drag: 0.7,
      ttl: 900 + Math.random() * 600,
      delay: delay + i * 35,
      size: 10 + Math.random() * 6,
      color,
      glyph: CODE[i % CODE.length],
      glow: true,
    });
  }
}
