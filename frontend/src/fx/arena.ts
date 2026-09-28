import { clamp, div, reducedMotion, spawn, type Point } from "./motion";
import { burst } from "./particles";

// Where things are in the arena, in percent of the 1920x800 frame (measured
// from the Blender camera like the rest of the arena CSS).
export const SPOT = {
  player: { x: 25, y: 56 },
  enemy: { x: 76.5, y: 54 },
  rift: { x: 48.5, y: 50 },
  playerShield: { x: 33, y: 55 },
  enemyShield: { x: 67.5, y: 54 },
  playerLabel: { x: 25, y: 30 },
  enemyLabel: { x: 76.5, y: 32 },
} satisfies Record<string, Point>;

export type Side = "player" | "enemy";

// The overlay every arena effect is drawn into: one absolutely positioned
// layer appended to .arena-stage, so effects can use the stage's percent
// and cqw units. React does not know about it and never touches it.
export function arenaLayer(stage: HTMLElement): HTMLElement {
  let layer = stage.querySelector<HTMLElement>(":scope > .fx-arena");
  if (!layer) {
    layer = div("fx-arena");
    layer.setAttribute("aria-hidden", "true");
    stage.appendChild(layer);
  }
  return layer;
}

// A spot in the arena as a viewport point, for the particle canvas.
export function toViewport(stage: HTMLElement, spot: Point): Point {
  const r = stage.getBoundingClientRect();
  return { x: r.left + (spot.x / 100) * r.width, y: r.top + (spot.y / 100) * r.height };
}

function place(el: HTMLElement, spot: Point) {
  el.style.left = `${spot.x}%`;
  el.style.top = `${spot.y}%`;
}

// ---- screen shake -------------------------------------------------------

const shaking = new WeakMap<Element, { animation: Animation; intensity: number }>();

// `intensity` 0..~2: 0.2 is a light tap, 1 a heavy blow, 2 Kernel Panic.
// A stronger shake replaces a running one; a weaker one leaves it alone.
export function shake(target: Element | null, intensity: number, delay = 0): void {
  if (!target || intensity <= 0 || reducedMotion()) return;
  window.setTimeout(() => {
    const running = shaking.get(target);
    if (running && running.animation.playState === "running" && running.intensity > intensity) return;
    running?.animation.cancel();
    const amp = clamp(intensity, 0, 2.2) * 9;
    const steps = Math.round(7 + intensity * 5);
    const frames: Keyframe[] = [];
    for (let i = 0; i <= steps; i++) {
      const decay = 1 - i / steps;
      const a = amp * decay * decay;
      const angle = Math.random() * Math.PI * 2;
      frames.push({
        transform:
          i === steps
            ? "none"
            : `translate(${(Math.cos(angle) * a).toFixed(1)}px, ${(Math.sin(angle) * a).toFixed(1)}px) rotate(${((Math.random() - 0.5) * a * 0.12).toFixed(2)}deg)`,
      });
    }
    const animation = target.animate(frames, { duration: 260 + intensity * 260, easing: "linear" });
    shaking.set(target, { animation, intensity });
  }, delay);
}

// ---- floating numbers ---------------------------------------------------

export type NumberKind = "damage" | "block" | "heal" | "crit" | "shielded";

export function floatNumber(
  stage: HTMLElement,
  side: Side,
  text: string,
  kind: NumberKind,
  { delay = 0, index = 0 }: { delay?: number; index?: number } = {},
): void {
  const el = div(`fx-number is-${kind}`, text);
  const base = side === "player" ? SPOT.playerLabel : SPOT.enemyLabel;
  // successive hits fan out so a combo doesn't stack on one spot
  const jitter = index === 0 ? 0 : ((index % 2 ? 1 : -1) * (2 + index * 1.4));
  place(el, { x: base.x + jitter, y: base.y + (index % 3) * 3 });
  const pop = kind === "crit" ? 1.6 : 1.25 + Math.min(index, 4) * 0.08;
  if (reducedMotion()) {
    spawn(arenaLayer(stage), el, [{ opacity: 1 }, { opacity: 1, offset: 0.7 }, { opacity: 0 }], { duration: 1100, delay });
    return;
  }
  spawn(
    arenaLayer(stage),
    el,
    [
      { opacity: 0, transform: "translate(-50%, 0) scale(0.4)" },
      { opacity: 1, transform: `translate(-50%, -30%) scale(${pop})`, offset: 0.12 },
      { opacity: 1, transform: "translate(-50%, -60%) scale(1)", offset: 0.3 },
      { opacity: 0, transform: `translate(-50%, -${kind === "crit" ? 110 : 190}%) scale(0.95)` },
    ],
    { duration: kind === "crit" ? 1500 : 1150, delay, easing: "cubic-bezier(.2,.8,.3,1)" },
  );
}

// "3 HITS · 12" under a multi-hit's numbers.
export function comboLabel(stage: HTMLElement, side: Side, hits: number, total: number, delay: number): void {
  const el = div("fx-combo");
  el.innerHTML = `<b>${hits}</b> HITS <span>· ${total}</span>`;
  const base = side === "player" ? SPOT.playerLabel : SPOT.enemyLabel;
  place(el, { x: base.x, y: base.y + 14 });
  spawn(
    arenaLayer(stage),
    el,
    reducedMotion()
      ? [{ opacity: 1 }, { opacity: 0 }]
      : [
          { opacity: 0, transform: "translate(-50%, 0) scale(2) skewX(-12deg)" },
          { opacity: 1, transform: "translate(-50%, 0) scale(1) skewX(-12deg)", offset: 0.12 },
          { opacity: 1, transform: "translate(-50%, 0) scale(1) skewX(-12deg)", offset: 0.75 },
          { opacity: 0, transform: "translate(-50%, -40%) scale(1) skewX(-12deg)" },
        ],
    { duration: 1300, delay, easing: "ease-out" },
  );
}

// ---- projectiles --------------------------------------------------------

// A glitchy data bolt shot out of the rift. `size` 1 is a regular exploit,
// bigger for heavier hits. Resolves when it lands.
export function bolt(
  stage: HTMLElement,
  from: Point,
  to: Point,
  { delay = 0, size = 1, duration = 160, color = "cyan" }: { delay?: number; size?: number; duration?: number; color?: "cyan" | "red" | "white" } = {},
): void {
  if (reducedMotion()) return;
  const el = div(`fx-bolt is-${color}`);
  place(el, from);
  el.style.setProperty("--size", String(size));
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  // percent of the stage -> cqw/cqh-free: the stage keeps its 2.4:1 aspect,
  // so a vertical percent is 1/2.4 of a horizontal one
  const angle = (Math.atan2(dy / 2.4, dx) * 180) / Math.PI;
  spawn(
    arenaLayer(stage),
    el,
    [
      { opacity: 0, transform: `translate(-50%, -50%) rotate(${angle}deg) scaleX(0.2)` },
      { opacity: 1, transform: `translate(-50%, -50%) rotate(${angle}deg) scaleX(1.3)`, offset: 0.2 },
      { opacity: 1, left: `${to.x}%`, top: `${to.y}%`, transform: `translate(-50%, -50%) rotate(${angle}deg) scaleX(0.6)` },
    ],
    { duration, delay, easing: "cubic-bezier(.55,0,.9,.6)" },
  );
}

// The flash and voxels where a hit lands.
export function impact(
  stage: HTMLElement,
  at: Point,
  { delay = 0, size = 1, color = "cyan" }: { delay?: number; size?: number; color?: "cyan" | "red" | "white" | "green" } = {},
): void {
  if (reducedMotion()) return;
  const ring = div(`fx-impact is-${color}`);
  place(ring, at);
  ring.style.setProperty("--size", String(size));
  spawn(
    arenaLayer(stage),
    ring,
    [
      { opacity: 1, transform: "translate(-50%, -50%) scale(0.2)" },
      { opacity: 0.9, transform: "translate(-50%, -50%) scale(1)", offset: 0.35 },
      { opacity: 0, transform: "translate(-50%, -50%) scale(1.5)" },
    ],
    { duration: 380, delay, easing: "ease-out" },
  );
  const palette = {
    cyan: ["#e6fcff", "#8ff2ef", "#4fd8e0", "#1a2e3e"],
    red: ["#ffd2a8", "#ff4d6a", "#c65a3a", "#2a0d10"],
    white: ["#ffffff", "#e6fcff", "#8ff2ef", "#ff4d6a"],
    green: ["#d6ffd9", "#8dffa0", "#7cae5a"],
  }[color];
  window.setTimeout(() => {
    burst(toViewport(stage, at), { count: Math.round(10 + size * 10), colors: palette, speed: 160 + size * 80, size: 3 + size * 1.2, gravity: 520 });
  }, delay);
}

// Brief colour flash of a fighter - the hit flash on top of the arena's own
// hit animation. Runs on the idle wrapper so it doesn't fight the <img>/<svg>
// transforms.
export function hitFlash(stage: HTMLElement, side: Side, { delay = 0, strength = 1 } = {}): void {
  if (reducedMotion()) return;
  const target = stage.querySelector(`.arena-idle.is-${side}`);
  if (!target) return;
  const glitch =
    side === "enemy"
      ? `brightness(${1 + 1.6 * strength}) drop-shadow(${-6 * strength}px 0 0 #4fd8e0) drop-shadow(${6 * strength}px 0 0 #ff4d6a)`
      : `brightness(${1 + strength}) drop-shadow(0 0 ${10 * strength}px #ff4d6a)`;
  target.animate([{ filter: "none" }, { filter: glitch, offset: 0.2 }, { filter: "none" }], {
    duration: 240,
    delay,
    easing: "steps(4, end)",
  });
}

// ---- shields ------------------------------------------------------------

const HEX_PATTERN = (id: string, color: string) => `
  <defs>
    <pattern id="${id}" width="17.32" height="30" patternUnits="userSpaceOnUse" patternTransform="scale(0.7)">
      <path d="M8.66 0 L17.32 5 L17.32 15 L8.66 20 L0 15 L0 5 Z M8.66 20 L8.66 30" fill="none" stroke="${color}" stroke-width="1.2"/>
    </pattern>
    <linearGradient id="${id}-fade" x1="0" x2="1">
      <stop offset="0" stop-color="${color}" stop-opacity="0.05"/>
      <stop offset="0.7" stop-color="${color}" stop-opacity="0.35"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0.8"/>
    </linearGradient>
  </defs>`;

let shieldSeq = 0;

// A curved firewall of hexagons in front of a fighter. `shatter` breaks it
// apart after a moment - an attack spent itself on the block.
export function shield(
  stage: HTMLElement,
  side: Side,
  { delay = 0, shatter = false, color = side === "player" ? "#4fd8e0" : "#ff9a4d" }: { delay?: number; shatter?: boolean; color?: string } = {},
): void {
  const id = `fx-hex-${++shieldSeq}`;
  const wrap = div(`fx-shield is-${side}`);
  const spot = side === "player" ? SPOT.playerShield : SPOT.enemyShield;
  place(wrap, spot);
  // the arc bulges towards the opponent
  const d = side === "player" ? "M10 0 Q 60 100 10 200 L 26 200 Q 76 100 26 0 Z" : "M70 0 Q 20 100 70 200 L 54 200 Q 4 100 54 0 Z";
  wrap.innerHTML = `<svg viewBox="0 0 80 200" preserveAspectRatio="none">${HEX_PATTERN(id, color)}
    <path d="${d}" fill="url(#${id}-fade)" />
    <path d="${d}" fill="url(#${id})" />
    <path d="${d}" fill="none" stroke="${color}" stroke-width="1.5" />
  </svg>`;
  const flip = side === "player" ? 1 : -1;
  const hold = shatter ? 380 : 1100;
  const keyframes: Keyframe[] = reducedMotion()
    ? [{ opacity: 0 }, { opacity: 0.8, offset: 0.2 }, { opacity: 0.8, offset: 0.8 }, { opacity: 0 }]
    : shatter
      ? [
          { opacity: 0, transform: `translate(-50%, -50%) scaleX(${0.2 * flip})`, filter: "brightness(2)" },
          { opacity: 1, transform: "translate(-50%, -50%) scaleX(1)", filter: "brightness(1)", offset: 0.4 },
          { opacity: 1, transform: "translate(-50%, -50%) scaleX(1.06)", filter: "brightness(2.5)", offset: 0.85 },
          { opacity: 0, transform: "translate(-50%, -50%) scaleX(1.25) skewY(4deg)", filter: "brightness(3)" },
        ]
      : [
          { opacity: 0, transform: "translate(-50%, -50%) scaleX(0.1)", filter: "brightness(3)" },
          { opacity: 1, transform: "translate(-50%, -50%) scaleX(1.1)", filter: "brightness(1.6)", offset: 0.18 },
          { opacity: 0.9, transform: "translate(-50%, -50%) scaleX(1)", filter: "brightness(1)", offset: 0.3 },
          { opacity: 0.75, transform: "translate(-50%, -50%) scaleX(1)", offset: 0.8 },
          { opacity: 0, transform: "translate(-50%, -50%) scaleX(0.9)" },
        ];
  spawn(arenaLayer(stage), wrap, keyframes, { duration: hold + 300, delay, easing: "ease-out" });

  if (shatter && !reducedMotion()) {
    window.setTimeout(() => {
      const r = stage.getBoundingClientRect();
      const cx = r.left + (spot.x / 100) * r.width;
      const cy = r.top + (spot.y / 100) * r.height;
      const h = r.height * 0.55;
      // shards fly back, away from the attacker
      burst({ x: cx, y: cy - h * 0.2 }, { count: 14, colors: [color, "#ffffff"], speed: 260, size: 6, gravity: 500 });
      burst({ x: cx, y: cy + h * 0.2 }, { count: 14, colors: [color, "#e6fcff"], speed: 260, size: 5, gravity: 500 });
      const crack = div(`fx-crack is-${side}`);
      place(crack, spot);
      spawn(arenaLayer(stage), crack, [{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: "steps(3, end)" });
    }, delay + hold * 0.85);
  }
}

// ---- full-arena overlays ----------------------------------------------

// Kernel Panic: the whole arena crashes into a bluescreen for a moment,
// torn by glitch bands.
export function bluescreen(stage: HTMLElement, enemyName: string, delay = 0): void {
  if (reducedMotion()) return;
  const layer = arenaLayer(stage);
  const bsod = div("fx-bsod");
  const code = (Math.abs([...enemyName].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) | 0, 7)) >>> 0)
    .toString(16)
    .toUpperCase()
    .padStart(8, "0");
  bsod.innerHTML = `<div class="fx-bsod-face">:(</div>
    <div class="fx-bsod-text">KERNEL PANIC - not syncing: fatal exception in ${escapeHtml(enemyName)}<br/>
    STOP 0x${code} &nbsp; PERMANENTS_DEREFERENCED<br/>dumping physical memory ... 100%</div>`;
  spawn(
    layer,
    bsod,
    [
      { opacity: 0, clipPath: "inset(48% 0 48% 0)" },
      { opacity: 1, clipPath: "inset(0 0 0 0)", offset: 0.08 },
      { opacity: 1, clipPath: "inset(0 0 0 0)", transform: "translateX(0)", offset: 0.45 },
      { opacity: 1, clipPath: "inset(0 0 35% 0)", transform: "translateX(-2%)", offset: 0.55 },
      { opacity: 0.9, clipPath: "inset(20% 0 0 0)", transform: "translateX(3%)", offset: 0.65 },
      { opacity: 0.6, clipPath: "inset(60% 0 10% 0)", transform: "translateX(-1%)", offset: 0.8 },
      { opacity: 0, clipPath: "inset(50% 0 50% 0)", transform: "none" },
    ],
    { duration: 950, delay, easing: "steps(18, end)" },
  );
  glitchBands(stage, { delay: delay + 450, count: 9 });
}

// Horizontal slices of the arena torn sideways - digital corruption.
export function glitchBands(stage: HTMLElement, { delay = 0, count = 5, color = "rgba(79, 216, 224, 0.5)" } = {}): void {
  if (reducedMotion()) return;
  const layer = arenaLayer(stage);
  for (let i = 0; i < count; i++) {
    const band = div("fx-band");
    band.style.top = `${Math.random() * 92}%`;
    band.style.height = `${2 + Math.random() * 9}%`;
    band.style.background = i % 3 === 0 ? "rgba(255, 77, 106, 0.45)" : color;
    const shift = (Math.random() - 0.5) * 30;
    spawn(
      layer,
      band,
      [
        { opacity: 0, transform: "translateX(0)" },
        { opacity: 1, transform: `translateX(${shift}%)`, offset: 0.3 },
        { opacity: 0.8, transform: `translateX(${-shift / 2}%)`, offset: 0.6 },
        { opacity: 0, transform: "translateX(0)" },
      ],
      { duration: 240 + Math.random() * 200, delay: delay + Math.random() * 260, easing: "steps(5, end)" },
    );
  }
}

// A coloured flash over the whole stage: white for a big impact, red
// around the edges when the boss lands a blow.
export function flash(stage: HTMLElement, kind: "white" | "red" | "green", { delay = 0, strength = 1 } = {}): void {
  if (reducedMotion()) return;
  const el = div(`fx-flash is-${kind}`);
  spawn(arenaLayer(stage), el, [{ opacity: 0 }, { opacity: clamp(strength, 0, 1), offset: 0.12 }, { opacity: 0 }], {
    duration: kind === "red" ? 650 : 380,
    delay,
    easing: "ease-out",
  });
}

// A thick beam from the rift into the enemy - Zero-Day's single huge hit.
export function beam(stage: HTMLElement, from: Point, to: Point, delay = 0): void {
  if (reducedMotion()) return;
  const el = div("fx-beam");
  el.style.left = `${from.x}%`;
  el.style.top = `${from.y}%`;
  el.style.width = `${to.x - from.x}%`;
  spawn(
    arenaLayer(stage),
    el,
    [
      { opacity: 0, transform: "translateY(-50%) scale(0, 0.3)" },
      { opacity: 1, transform: "translateY(-50%) scale(1, 1.4)", offset: 0.25 },
      { opacity: 1, transform: "translateY(-50%) scale(1, 1)", offset: 0.55 },
      { opacity: 0, transform: "translateY(-50%) scale(1, 0.05)" },
    ],
    { duration: 520, delay, easing: "cubic-bezier(.2,.9,.3,1)" },
  );
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}
