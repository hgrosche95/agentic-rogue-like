import { useLayoutEffect, useRef } from "react";
import type { Card } from "../api";
import { ART_KEY, ART_SIZE, artFor } from "../pixel/cardArt";
import { COLORS } from "../pixel/palette";

// The card's 24x24 motif on a canvas, scaled up by the largest whole number
// that fits the height of the box it sits in (.card-art) - every motif pixel
// becomes an exact square of screen pixels, never smoothed. Drawn at the
// screen's own pixel density, so it stays crisp on a high-DPI display too.
export function CardArt({ card }: { card: Pick<Card, "name" | "type"> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const raster = artFor(card);

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    const box = canvas?.parentElement;
    if (!canvas || !box) return;
    let drawn = "";
    const draw = () => {
      const scale = Math.max(1, Math.floor(box.clientHeight / ART_SIZE));
      const dpr = window.devicePixelRatio || 1;
      // screen pixels per motif pixel - whole, so no pixel comes out wider,
      // and rounded down, so the motif never outgrows its box (at a 125 %
      // display, 2x becomes 2 screen pixels, not 3)
      const k = Math.max(1, Math.floor(scale * dpr));
      const key = `${scale}|${k}`;
      if (key === drawn) return;
      drawn = key;
      canvas.width = canvas.height = ART_SIZE * k;
      canvas.style.width = canvas.style.height = `${(ART_SIZE * k) / dpr}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      raster.forEach((row, y) => {
        for (let x = 0; x < row.length; x++) {
          const color = ART_KEY[row[x]];
          if (color === undefined) continue; // "." - see-through
          ctx.fillStyle = COLORS[color];
          ctx.fillRect(x * k, y * k, k, k);
        }
      });
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(box);
    return () => observer.disconnect();
  }, [raster]);

  return <canvas ref={canvasRef} className="card-art-canvas" />;
}
