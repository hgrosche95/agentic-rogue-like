import type { CSSProperties, ReactNode } from "react";
import type { HpExchange } from "../hooks/useHpExchange";
import { CombatMonitor } from "./CombatMonitor";

// Three full-frame layers rendered from the same Blender camera
// (assets/blender/arena.blend): stacking them reproduces the scene exactly,
// while the two fighters stay separate elements that can be animated.
const LAYERS = {
  background: "/assets/lab-background.png",
  player: "/assets/lab-player.png",
  enemy: "/assets/lab-enemy.png",
};

const PIXEL_COUNT = 16;

function classes(...names: (string | false)[]): string {
  return names.filter(Boolean).join(" ");
}

function DamagePopup({ side, delta }: { side: "player" | "enemy"; delta: number }) {
  const isHeal = delta > 0;
  return (
    <span className={`arena-popup is-${side} ${isHeal ? "is-heal" : "is-damage"}`}>
      {isHeal ? `+${delta}` : delta}
    </span>
  );
}

// Voxel shards knocked out of the enemy. Spread with the golden angle rather
// than Math.random() so rendering stays pure and every hit looks the same.
function PixelBurst() {
  return (
    <>
      {Array.from({ length: PIXEL_COUNT }, (_, i) => {
        const angle = (i * 137.5 * Math.PI) / 180;
        const distance = 40 + ((i * 29) % 70);
        const style = {
          "--dx": `${Math.cos(angle) * distance + 30}px`,
          "--dy": `${Math.sin(angle) * distance}px`,
          animationDelay: `${200 + i * 15}ms`,
        } as CSSProperties;
        return <span key={i} className={`arena-pixel${i % 3 === 0 ? " is-dark" : ""}`} style={style} />;
      })}
    </>
  );
}

// `children` is drawn on top of the scene - the HUD lives there, in the two
// upper corners left free by the monitor.
export function CombatArena({
  exchange,
  log,
  children,
}: {
  exchange: HpExchange | null;
  log: string[];
  children?: ReactNode;
}) {
  const playerStruck = exchange !== null && exchange.enemyDelta < 0;
  const enemyStruck = exchange !== null && exchange.playerDelta < 0;
  const playerHealed = exchange !== null && exchange.playerDelta > 0;

  return (
    <div className="arena-stage">
      <img className="arena-layer" src={LAYERS.background} alt="" />
      {/* key remounts the fighters on every HP change so their CSS animations replay */}
      <img
        key={`player-${exchange?.id}`}
        className={classes("arena-layer", "arena-player", playerStruck && "is-lunging", enemyStruck && "is-hit", playerHealed && "is-healed")}
        src={LAYERS.player}
        alt="Dr. Chronos"
      />
      <img
        key={`enemy-${exchange?.id}`}
        className={classes("arena-layer", "arena-enemy", enemyStruck && "is-lunging", playerStruck && "is-hit")}
        src={LAYERS.enemy}
        alt=""
      />
      <CombatMonitor lines={log} />
      {exchange && (
        <div key={exchange.id} className="arena-fx" aria-hidden="true">
          {exchange.enemyDelta !== 0 && <DamagePopup side="enemy" delta={exchange.enemyDelta} />}
          {exchange.playerDelta !== 0 && <DamagePopup side="player" delta={exchange.playerDelta} />}
          {playerStruck && (
            <>
              <span className="arena-slash" />
              <PixelBurst />
            </>
          )}
          {enemyStruck && <span className="arena-beam" />}
        </div>
      )}
      {children}
    </div>
  );
}
