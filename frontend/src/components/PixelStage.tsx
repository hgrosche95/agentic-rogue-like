import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { HEIGHT, WIDTH } from "../pixel/layout";
import { PixelScene } from "../pixel/scene";

const STEP_MS = 1000 / 60;

// Hosts a PixelScene: runs its fixed 60 Hz simulation, and blits its
// WIDTH x HEIGHT frame onto a display canvas.
//
// fit="integer" (the combat arena) scales by the largest whole factor of
// device pixels that fits, so every logical pixel is an exact square; the
// frame is centered and `children` (HTML overlays placed in % of the frame)
// sit on exactly that frame. fit="fill" (the intro, which zooms its camera
// with CSS anyway) just stretches to the container.
export function PixelStage({
  fit = "integer",
  className,
  onScene,
  children,
  ref,
}: {
  fit?: "integer" | "fill";
  className?: string;
  // the scene, once created - to set its enemy/status and trigger events
  onScene?: (scene: PixelScene) => void;
  children?: ReactNode;
  ref?: Ref<HTMLDivElement>;
}) {
  const outerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [scene] = useState(() => new PixelScene());
  const [size, setSize] = useState({ css: 0, factor: 1, cssW: 0, cssH: 0 });

  useLayoutEffect(() => {
    onScene?.(scene);
  }, [scene, onScene]);

  useLayoutEffect(() => {
    const outer = outerRef.current;
    if (!outer) return;
    const measure = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = outer.clientWidth;
      const h = outer.clientHeight || w / (WIDTH / HEIGHT);
      if (fit === "fill") {
        setSize({ css: 0, factor: 0, cssW: w, cssH: h });
        return;
      }
      const factor = Math.max(1, Math.floor(Math.min((w * dpr) / WIDTH, (h * dpr) / HEIGHT)));
      setSize({ css: factor / dpr, factor, cssW: (WIDTH * factor) / dpr, cssH: (HEIGHT * factor) / dpr });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(outer);
    return () => observer.disconnect();
  }, [fit]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    const frame = (now: number) => {
      acc += Math.min(now - last, 250);
      last = now;
      let steps = 0;
      while (acc >= STEP_MS && steps < 8) {
        scene.step();
        acc -= STEP_MS;
        steps++;
      }
      if (steps === 8) acc = 0;
      scene.draw();
      const w = canvas.width;
      const h = canvas.height;
      const kx = w / WIDTH;
      const ky = h / HEIGHT;
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(scene.canvas, Math.round(scene.shakeX * kx), Math.round(scene.shakeY * ky), w, h);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [scene]);

  const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const pixelW = fit === "fill" ? Math.max(WIDTH, Math.round(size.cssW * dpr)) : WIDTH * size.factor;
  const pixelH = fit === "fill" ? Math.max(HEIGHT, Math.round(size.cssH * dpr)) : HEIGHT * size.factor;

  return (
    <div ref={outerRef} className={`pixel-stage${className ? ` ${className}` : ""}`}>
      <div
        ref={ref}
        className="pixel-frame"
        style={fit === "fill" ? undefined : { width: size.cssW, height: size.cssH }}
      >
        <canvas ref={canvasRef} className="pixel-canvas" width={pixelW} height={pixelH} aria-hidden="true" />
        {children}
      </div>
    </div>
  );
}
