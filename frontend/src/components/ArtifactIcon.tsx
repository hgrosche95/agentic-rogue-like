import type { ReactNode } from "react";

// One small line drawing per artifact, keyed by the server's artifact id
// (artifacts.py). Plain strokes in currentColor, like the map's sword glyph,
// so the color follows the surrounding text instead of an emoji palette.
// All drawn in a 16x16 box centred on 0,0.
const ICONS: Record<string, ReactNode> = {
  // stacked cache lines with a fast-forward tick
  "cache-line": (
    <>
      <path d="M-6 -4 H3 M-6 0 H3 M-6 4 H3" />
      <path d="M4.5 -2 L7 0 L4.5 2" />
    </>
  ),
  // a script bracket around a plus
  "self-healing-script": (
    <>
      <path d="M-3.5 -6.5 Q-6 -6.5 -6 -4 V-1.5 L-7 0 L-6 1.5 V4 Q-6 6.5 -3.5 6.5" />
      <path d="M3.5 -6.5 Q6 -6.5 6 -4 V-1.5 L7 0 L6 1.5 V4 Q6 6.5 3.5 6.5" />
      <path d="M0 -3 V3 M-3 0 H3" />
    </>
  ),
  // a chip with pins and a lightning bolt
  "overclocked-cpu": (
    <>
      <rect x="-4.5" y="-4.5" width="9" height="9" rx="1" />
      <path d="M-2 -7 V-4.5 M2 -7 V-4.5 M-2 4.5 V7 M2 4.5 V7 M-7 -2 H-4.5 M-7 2 H-4.5 M4.5 -2 H7 M4.5 2 H7" />
      <path d="M0.8 -3 L-1.5 0.5 H1.5 L-0.8 3" />
    </>
  ),
  // a narrowing cone ending in a focused eye
  "tunnel-vision": (
    <>
      <path d="M-7 -5 L2 -1 M-7 5 L2 1" />
      <circle cx="4.5" cy="0" r="2.5" />
      <circle cx="4.5" cy="0" r="0.6" />
    </>
  ),
  // cooling fins on a base plate
  "heat-sink": (
    <>
      <path d="M-7 5.5 H7" />
      <path d="M-5 5.5 V-5 M-1.7 5.5 V-6.5 M1.7 5.5 V-6.5 M5 5.5 V-5" />
    </>
  ),
  // a RAM stick with notches and chips
  "extra-ram": (
    <>
      <path d="M-7.5 -3.5 H7.5 V3.5 H1 V2 H-1 V3.5 H-7.5 Z" />
      <path d="M-5.5 -1.5 H-3 V1 H-5.5 Z M-1.2 -1.5 H1.2 V0.5 H-1.2 Z M3 -1.5 H5.5 V1 H3 Z" />
    </>
  ),
  // a door ajar with an arrow slipping in
  backdoor: (
    <>
      <path d="M-1 -7 H6 V7 H-1" />
      <path d="M-1 -7 L3 -5.5 V8.5 L-1 7 Z" />
      <path d="M-7.5 0 H0 M-2.5 -2.5 L0 0 L-2.5 2.5" />
    </>
  ),
  // a pit with spikes
  tarpit: (
    <>
      <path d="M-7 6 H7" />
      <path d="M-6 6 L-4.5 -2 L-3 6 M-1.5 6 L0 -5 L1.5 6 M3 6 L4.5 -2 L6 6" />
    </>
  ),
  // a riveted shield
  "titanium-chassis": (
    <>
      <path d="M0 -7.5 L6.5 -5 V0 Q6.5 5 0 7.5 Q-6.5 5 -6.5 0 V-5 Z" />
      <path d="M-6.5 -1.5 H6.5" />
      <circle cx="-3" cy="2.5" r="0.7" />
      <circle cx="3" cy="2.5" r="0.7" />
    </>
  ),
  // a patch stitched onto a board
  "firmware-patch": (
    <>
      <rect x="-5" y="-5" width="10" height="10" rx="1.5" transform="rotate(45)" />
      <path d="M-2 -2 L2 2 M2 -2 L-2 2" />
    </>
  ),
  // a medkit case with a cross
  "medkit-exe": (
    <>
      <rect x="-7" y="-4" width="14" height="10" rx="1.5" />
      <path d="M-2.5 -4 V-6.5 H2.5 V-4" />
      <path d="M0 -1.5 V3.5 M-2.5 1 H2.5" />
    </>
  ),
  // a sharpened arrowhead
  "sharpened-payloads": (
    <>
      <path d="M7 -7 L-1 -4.5 L4.5 1 Z" />
      <path d="M1.8 -1.8 L-7 7" />
    </>
  ),
  // a hex nut
  "hardened-kernel": (
    <>
      <path d="M0 -7.5 L6.5 -3.75 V3.75 L0 7.5 L-6.5 3.75 V-3.75 Z" />
      <circle cx="0" cy="0" r="2.8" />
    </>
  ),
  // a crescent moon with a z
  "sleep-mode": (
    <>
      <path d="M1 -6.5 A6.5 6.5 0 1 0 6.5 3 A5 5 0 0 1 1 -6.5 Z" />
      <path d="M3 -7 H6.5 L3 -3.5 H6.5" />
    </>
  ),
  // a cracked gem
  "glass-cannon": (
    <>
      <path d="M-4 -6.5 H4 L7 -2 L0 7 L-7 -2 Z" />
      <path d="M-7 -2 H7 M-1 -2 L1.5 1.5 L-0.5 4" />
    </>
  ),
  // an hourglass
  "lag-spike": (
    <>
      <path d="M-5 -7 H5 M-5 7 H5" />
      <path d="M-4 -7 Q-4 -2 0 0 Q4 2 4 7 M4 -7 Q4 -2 0 0 Q-4 2 -4 7" />
    </>
  ),
  // a stopwatch
  "watchdog-timer": (
    <>
      <circle cx="0" cy="1.5" r="5.5" />
      <path d="M-1.5 -6.5 H1.5 M0 -6.5 V-4 M0 1.5 L2.5 -1" />
      <path d="M4.5 -4.5 L5.8 -5.8" />
    </>
  ),
  // a power button
  "quick-boot": (
    <>
      <path d="M-4.2 -4.2 A6 6 0 1 0 4.2 -4.2" />
      <path d="M0 -7 V0" />
    </>
  ),
  // a speed gauge held low
  "rate-limiter": (
    <>
      <path d="M-7 3 A7 7 0 0 1 7 3" />
      <path d="M0 3 L-4 -1.5" />
      <circle cx="0" cy="3" r="1" />
      <path d="M-7 6 H7" />
    </>
  ),
  // a pair of fangs with a drop
  "vampire-process": (
    <>
      <path d="M-7 -5 H7" />
      <path d="M-5 -5 L-3.5 1 L-2 -5 M2 -5 L3.5 1 L5 -5" />
      <path d="M0 2 Q-1.8 4.5 0 6.5 Q1.8 4.5 0 2 Z" />
    </>
  ),
};

// Anything the frontend doesn't know yet (a newer server) gets a plain gem.
const FALLBACK = <path d="M0 -6.5 L5.5 0 L0 6.5 L-5.5 0 Z" />;

export function ArtifactIcon({ id, size = 16 }: { id: string; size?: number }) {
  return (
    <svg
      className="artifact-icon"
      viewBox="-8.5 -8.5 17 17"
      width={size}
      height={size}
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICONS[id] ?? FALLBACK}
    </svg>
  );
}
