import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from "react";
import type { HpExchange } from "../hooks/useHpExchange";
import { CombatMonitor } from "./CombatMonitor";
import { EnemyMonster } from "./EnemyMonster";

// Full-frame layers rendered from the same Blender camera
// (assets/blender/arena.blend): stacking them reproduces the scene exactly,
// while the player stays a separate element that can be animated. The enemy
// is LLM-generated, so it is drawn procedurally in the same frame instead.
const LAYERS = {
  background: "/assets/lab-background.webp",
  player: "/assets/lab-player.webp",
};

export interface ArenaEnemy {
  name: string;
  maxHp: number;
  attack: number;
  setting: string;
}

const PIXEL_COUNT = 16;
const DEATH_PIXEL_COUNT = 28;

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

// The defeated enemy coming apart: a flash as it collapses and a cloud of
// voxels drifting up from where it stood. Delayed in CSS until the killing
// blow has landed.
function DeathBurst() {
  return (
    <div className="arena-fx is-death" aria-hidden="true">
      <span className="arena-death-flash" />
      {Array.from({ length: DEATH_PIXEL_COUNT }, (_, i) => {
        const angle = (i * 137.5 * Math.PI) / 180;
        const style = {
          "--dx": `${Math.cos(angle) * (30 + ((i * 23) % 90))}px`,
          "--dy": `${-60 - ((i * 37) % 110)}px`,
          left: `${70 + ((i * 7) % 13)}%`,
          top: `${40 + ((i * 11) % 42)}%`,
          animationDelay: `${1200 + ((i * 53) % 500)}ms`,
        } as CSSProperties;
        return <span key={i} className={`arena-pixel is-dissolving${i % 3 === 0 ? " is-dark" : ""}`} style={style} />;
      })}
    </div>
  );
}

// Living energy over the dimensional rift baked into the background: a glow
// strip whose streaks flow along the tear, bent by an animated turbulence
// filter. Pure CSS/SVG, so it costs no extra download.
function PortalRift() {
  return (
    <div className="arena-rift" aria-hidden="true">
      <svg className="arena-rift-defs" width="0" height="0">
        <filter id="arena-rift-warp" x="-20%" y="0" width="140%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.02 0.09" numOctaves="2" seed="3">
            <animate attributeName="baseFrequency" dur="7s" values="0.02 0.09;0.03 0.06;0.02 0.09" repeatCount="indefinite" />
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" scale="14" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </svg>
      <span className="arena-rift-glow" />
      <span className="arena-rift-streaks" />
    </div>
  );
}

// `children` is drawn on top of the scene - the HUD lives there, in the two
// upper corners left free by the monitor.
export function CombatArena({
  enemy,
  exchange,
  log,
  slain = false,
  onContinue,
  children,
}: {
  enemy: ArenaEnemy;
  exchange: HpExchange | null;
  log: string[];
  slain?: boolean;
  onContinue?: () => void;
  children?: ReactNode;
}) {
  const playerStruck = exchange !== null && exchange.enemyDelta < 0;
  const enemyStruck = exchange !== null && exchange.playerDelta < 0;
  const playerHealed = exchange !== null && exchange.playerDelta > 0;
  const playerRef = useRef<HTMLImageElement>(null);
  const enemyRef = useRef<SVGSVGElement>(null);

  // Replay the fighters' one-shot animations on every HP change, even when
  // two hits in a row keep the same class. Restarting them in place instead
  // of remounting the <img> matters: a fresh <img> paints empty for a frame
  // or two until the PNG is decoded again, which made the fighters flicker.
  // setAttribute rather than className, since the enemy is an <svg>.
  useLayoutEffect(() => {
    for (const el of [playerRef.current, enemyRef.current]) {
      if (!el) continue;
      const className = el.getAttribute("class") ?? "";
      el.setAttribute("class", "arena-layer");
      void el.getBoundingClientRect(); // flush styles so the re-added classes start fresh
      el.setAttribute("class", className);
    }
  }, [exchange?.id]);

  return (
    <div className="arena-stage">
      <img className="arena-layer" src={LAYERS.background} alt="" />
      <PortalRift />
      {/* The wrappers carry the looping idle motion; the images inside keep the
          one-shot combat animations, so both can run at once. */}
      <div className="arena-idle is-player">
        <img
          ref={playerRef}
          className={classes("arena-layer", "arena-player", playerStruck && "is-lunging", enemyStruck && "is-hit", playerHealed && "is-healed")}
          src={LAYERS.player}
          alt="Dr. Chronos"
        />
      </div>
      <div className={classes("arena-idle", "is-enemy", slain && "is-dying")}>
        <EnemyMonster
          ref={enemyRef}
          className={classes("arena-layer", "arena-enemy", enemyStruck && "is-lunging", playerStruck && "is-hit")}
          name={enemy.name}
          maxHp={enemy.maxHp}
          attack={enemy.attack}
          setting={enemy.setting}
        />
      </div>
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
      {slain && <DeathBurst />}
      {slain && (
        <div className="arena-victory">
          <span className="arena-victory-title">{enemy.name} defeated</span>
          <button type="button" className="arena-continue" onClick={onContinue}>
            Continue
          </button>
        </div>
      )}
    </div>
  );
}
