import { useEffect, useMemo, useRef, type CSSProperties } from "react";
import { COLORS } from "../pixel/palette";
import { enemySprite, type EnemySpec } from "../pixel/enemySprite";

// An enemy's pixel sprite on its own canvas, outside the arena - the empty
// rows above its head cut, scaled by a whole factor (CSS --w / --h, drawn
// pixelated by the caller's class).
export function PixelEnemy({ spec, scale, className }: { spec: EnemySpec; scale: number; className: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const { name, maxHp, attack, setting, bodyShape, feature, finalBoss } = spec;
  const sprite = useMemo(
    () => enemySprite({ name, maxHp, attack, setting, bodyShape, feature, finalBoss }),
    [name, maxHp, attack, setting, bodyShape, feature, finalBoss],
  );
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, sprite.w, sprite.h - sprite.top);
    for (let y = sprite.top; y < sprite.h; y++) {
      for (let x = 0; x < sprite.w; x++) {
        const p = sprite.pixels[y * sprite.w + x];
        if (!p) continue;
        ctx.fillStyle = COLORS[p - 1];
        ctx.fillRect(x, y - sprite.top, 1, 1);
      }
    }
  }, [sprite]);
  return (
    <canvas
      ref={ref}
      className={className}
      width={sprite.w}
      height={sprite.h - sprite.top}
      style={{ "--w": `${sprite.w * scale}px`, "--h": `${(sprite.h - sprite.top) * scale}px` } as CSSProperties}
      aria-hidden="true"
    />
  );
}
