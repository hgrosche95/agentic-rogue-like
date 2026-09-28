// Small shared helpers for the effects in this folder.

export function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

// Run `fn` after `ms`; effects are fire-and-forget, so nothing needs to
// cancel these - every step checks that its elements still exist.
export function after(ms: number, fn: () => void): void {
  if (ms <= 0) fn();
  else window.setTimeout(fn, ms);
}

export interface Point {
  x: number;
  y: number;
}

export function centerOf(el: Element): Point {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

// Appends `el` to `parent`, plays the keyframes and removes it again.
export function spawn(
  parent: Element,
  el: HTMLElement | SVGElement,
  keyframes: Keyframe[],
  options: KeyframeAnimationOptions,
): Animation {
  parent.appendChild(el);
  const animation = el.animate(keyframes, { fill: "both", ...options });
  const done = () => el.remove();
  animation.onfinish = done;
  animation.oncancel = done;
  return animation;
}

export function div(className: string, text?: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
