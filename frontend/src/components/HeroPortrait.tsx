import { useEffect, useRef, type RefObject } from "react";
import { FLOOR, PLAYER_X } from "../pixel/layout";
import type { ArenaHandle } from "./CombatArena";

// The square of the pixel scene around the hero's head (both heroes stand
// at PLAYER_X with their heads in the same place, see pixel/scene.ts), in
// logical pixels.
const SIZE = 22;
const LEFT = PLAYER_X - 12;
const TOP = FLOOR - 44;

// The hero's portrait in the HUD: their head, copied live out of the arena
// scene every frame - so it breathes, types, takes hits (the white flash)
// and wears the scene's light just as the figure does. Copying is a single
// 22 x 22 drawImage, cheap enough for every frame.
export function HeroPortrait({ arena }: { arena: RefObject<ArenaHandle | null> }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    let raf = 0;
    const frame = () => {
      const scene = arena.current?.scene();
      if (scene) {
        ctx.clearRect(0, 0, SIZE, SIZE);
        ctx.drawImage(scene.canvas, LEFT, TOP, SIZE, SIZE, 0, 0, SIZE, SIZE);
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [arena]);
  return <canvas ref={ref} className="hero-portrait" width={SIZE} height={SIZE} aria-hidden="true" />;
}
