import { useEffect, useRef, type CSSProperties } from "react";

// A small pixel scene over a room that isn't a fight: the safehouse (a
// server rack, a cot, a lamp, a terminal and a steaming mug) and an
// anomaly (a rift with a traveller beside it). Drawn on a 240x56 canvas
// and scaled up crisp; a few pixels move - LEDs blink, the steam rises,
// the rift breathes - unless motion is reduced. A terminal line under it
// types itself out (CSS).
const W = 240;
const H = 56;
const FRAME_MS = 280;

type Kind = "rest" | "event";

function draw(g: CanvasRenderingContext2D, kind: Kind, frame: number): void {
  const R = (x: number, y: number, w: number, h: number, col: string) => {
    g.fillStyle = col;
    g.fillRect(x, y, w, h);
  };
  const dither = (x: number, y: number, w: number, h: number, col: string, every = 2) => {
    g.fillStyle = col;
    for (let j = 0; j < h; j++) for (let i = j % 2; i < w; i += every) g.fillRect(x + i, y + j, 1, 1);
  };
  g.clearRect(0, 0, W, H);
  if (kind === "rest") {
    R(0, 0, W, H, "#0b0a1e");
    for (let x = 0; x < W; x += 24) {
      R(x, 0, 23, 40, "#13112c");
      R(x, 0, 23, 1, "#1d1a40");
    }
    R(0, 40, W, 16, "#0f0d24");
    dither(0, 40, W, 3, "#1b1840");
    // the server rack, its LEDs blinking
    R(14, 6, 26, 34, "#191637");
    R(14, 6, 26, 1, "#2a2660");
    for (let y = 10; y < 38; y += 4) {
      R(17, y, 20, 2, "#0b0a1e");
      R(18, y, 1, 1, "#34e7ff");
      const on = (y + frame * 3) % 12 !== 0;
      R(21, y, 1, 1, on ? (y % 8 ? "#5dff9b" : "#ff4f8b") : "#0b0a1e");
    }
    // the cot
    R(62, 32, 56, 5, "#2e2a57");
    R(62, 30, 56, 3, "#3ddc84");
    dither(64, 30, 52, 3, "#2faa66", 3);
    R(64, 27, 12, 4, "#d8d4ff");
    R(62, 37, 2, 4, "#191637");
    R(116, 37, 2, 4, "#191637");
    // the lamp and its light
    R(138, 6, 1, 8, "#3a3670");
    R(134, 14, 9, 3, "#ffcf4d");
    for (let j = 0; j < 22; j++) dither(138 - j, 17 + j, 2 * j + 1, 1, "rgba(255,207,77,0.18)", 3);
    // desk, terminal, mug
    R(150, 30, 60, 3, "#3a2a1a");
    R(152, 33, 2, 8, "#2a1e12");
    R(206, 33, 2, 8, "#2a1e12");
    R(162, 14, 30, 16, "#191637");
    R(164, 16, 26, 11, "#05301c");
    for (let y = 18; y < 26; y += 2) R(166, y, 6 + ((y * 7 + frame) % 14), 1, "#5dff9b");
    R(176, 30, 6, 1, "#191637");
    R(198, 24, 6, 6, "#d8d4ff");
    R(204, 25, 2, 3, "#d8d4ff");
    R(199, 25, 4, 1, "#6a3b1e");
    for (let k = 0; k < 6; k++) {
      const rise = (k + frame) % 6;
      R(199 + ((k + frame) % 2) * 2, 22 - rise, 1, 1, `rgba(255,255,255,${0.4 - rise * 0.06})`);
    }
  } else {
    R(0, 0, W, H, "#0a0820");
    dither(0, 30, W, 26, "#16123a");
    dither(0, 42, W, 14, "#221a52", 2);
    // the rift, breathing
    const cx = 120;
    const cy = 26;
    const breath = frame % 4 === 0 ? 1 : 0;
    for (let r = 20 + breath; r > 0; r--) {
      const col = r > 14 ? "#3b1f7a" : r > 8 ? "#7a3bff" : r > 3 ? "#c48bff" : "#f2e6ff";
      g.fillStyle = col;
      for (let a = 0; a < 64; a++) {
        const t = (a / 64) * Math.PI * 2;
        g.fillRect(Math.round(cx + Math.cos(t) * r * 0.55), Math.round(cy + Math.sin(t) * r), 1, 1);
      }
    }
    // glitch slices, shifting
    for (let k = 0; k < 7; k++) {
      const y = 6 + k * 7;
      R(cx - 30 + ((k * 13 + frame * 5) % 17), y, 10 + ((k * 5) % 12), 1, k % 2 ? "#34e7ff" : "#ff4f8b");
    }
    // a traveller with a heavy pack
    const fx = 82;
    const fy = 44;
    R(fx, fy - 18, 6, 6, "#c9a27a");
    R(fx - 1, fy - 19, 8, 2, "#2e2a57");
    R(fx - 1, fy - 12, 8, 10, "#3a3670");
    R(fx - 7, fy - 13, 7, 11, "#6a4a2a");
    R(fx - 6, fy - 12, 5, 2, "#8a6a3a");
    R(fx, fy - 2, 2, 6, "#1d1a40");
    R(fx + 4, fy - 2, 2, 6, "#1d1a40");
    R(fx + 6, fy - 9, 2, 5, "#c9a27a");
    // a question floating over it
    const q = ["01110", "10001", "00010", "00100", "00100", "00000", "00100"];
    const bob = frame % 2;
    q.forEach((row, j) =>
      [...row].forEach((b, i) => b === "1" && R(156 + i * 2, 8 + bob + j * 2, 2, 2, "#c48bff")),
    );
  }
  // scanlines
  for (let y = 0; y < H; y += 2) R(0, y, W, 1, "rgba(0,0,0,0.18)");
}

export function RoomHeader({ kind, line }: { kind: Kind; line: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const g = ref.current?.getContext("2d");
    if (!g) return;
    let frame = 0;
    draw(g, kind, frame);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => draw(g, kind, ++frame), FRAME_MS);
    return () => window.clearInterval(timer);
  }, [kind]);
  return (
    <div className={`room-header is-${kind}`} aria-hidden="true">
      <canvas ref={ref} width={W} height={H} />
      <span className="room-header-line" style={{ "--chars": line.length + 2 } as CSSProperties}>
        &gt; {line}
      </span>
    </div>
  );
}
