import { useEffect, useRef } from "react";

// Behind the title: the AGI reading its own code - faint columns of hex
// sliding down, a few of them lit where it is "thinking". Drawn on one
// canvas at a low frame rate; held still for reduced motion.
const CELL = 18;
const FPS = 14;
const GLYPHS = "0123456789ABCDEF";

export function TitleBackdrop() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let cols: { y: number; speed: number; hot: number }[] = [];
    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientHeight * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.ceil(canvas.clientWidth / CELL);
      cols = Array.from({ length: n }, () => ({
        y: Math.random() * canvas.clientHeight,
        speed: 0.3 + Math.random() * 0.9,
        hot: Math.random() < 0.12 ? 1 : 0,
      }));
    };
    const draw = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);
      ctx.font = `600 ${CELL - 6}px Rajdhani, monospace`;
      ctx.textAlign = "center";
      cols.forEach((col, i) => {
        const x = i * CELL + CELL / 2;
        // a short trail of glyphs above the head of each column
        for (let k = 0; k < 14; k++) {
          const y = col.y - k * CELL;
          if (y < -CELL || y > h + CELL) continue;
          const fade = 1 - k / 14;
          ctx.fillStyle = col.hot && k === 0 ? `rgba(255, 61, 139, ${0.55 * fade})` : `rgba(52, 231, 255, ${0.13 * fade})`;
          ctx.fillText(GLYPHS[(i * 7 + Math.floor(y / CELL) * 3) % 16], x, y);
        }
        if (!reduced) {
          col.y += col.speed * CELL * 0.25;
          if (col.y - 14 * CELL > h) {
            col.y = -Math.random() * h * 0.5;
            col.hot = Math.random() < 0.12 ? 1 : 0;
          }
        }
      });
    };
    resize();
    draw();
    const observer = new ResizeObserver(() => {
      resize();
      draw();
    });
    observer.observe(canvas);
    if (reduced) return () => observer.disconnect();
    const timer = window.setInterval(draw, 1000 / FPS);
    return () => {
      window.clearInterval(timer);
      observer.disconnect();
    };
  }, []);
  return <canvas ref={ref} className="title-backdrop" aria-hidden="true" />;
}
