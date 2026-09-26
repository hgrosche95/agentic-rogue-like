import { useLayoutEffect, useRef, type CSSProperties, type ReactNode } from "react";
import type { HpExchange } from "../hooks/useHpExchange";
import { CombatMonitor } from "./CombatMonitor";
import { EnemyMonster } from "./EnemyMonster";
import type { HackerCommand } from "../hackerCommands";

// Full-frame layers rendered from the same Blender camera
// (assets/blender/arena.blend): stacking them reproduces the scene exactly,
// while the player stays a separate element that can be animated. The rig -
// Dr. Chronos' desk, keyboard and the cable into the rift - comes from the
// blend's "Rig" view layer. The enemy is LLM-generated, so it is drawn
// procedurally in the same frame instead.
const LAYERS = {
  background: "/assets/lab-background.webp",
  player: "/assets/lab-player.webp",
  playerTyping: "/assets/lab-player-typing.webp",
  rig: "/assets/lab-rig.webp",
};

// The cable's centre line from the keyboard to the rift, in pixels of the
// 1920x800 render, projected from the blend with world_to_camera_view.
const CABLE_POINTS = "630,473 671,520 680,585 681,651 687,708 705,716 753,717 814,717 868,722 932,720";

export interface ArenaEnemy {
  name: string;
  maxHp: number;
  attack: number;
  setting: string;
}

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
          animationDelay: `${500 + i * 15}ms`,
        } as CSSProperties;
        return <span key={i} className={`arena-pixel${i % 3 === 0 ? " is-dark" : ""}`} style={style} />;
      })}
    </>
  );
}

// An attack leaving the keyboard: a pulse of light racing down the cable
// into the rift, from where it strikes the enemy.
function CablePulse() {
  return (
    <svg className="arena-cable" viewBox="0 0 1920 800">
      <polyline points={CABLE_POINTS} pathLength={100} />
    </svg>
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
  commands,
  typing,
  children,
}: {
  enemy: ArenaEnemy;
  exchange: HpExchange | null;
  log: string[];
  commands: HackerCommand[];
  typing: boolean;
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
      {/* The wrapper carries the looping idle motion; the images inside keep
          the one-shot combat animations, so both can run at once. The rig
          sits in it too, under him, so his hands stay on the keys while he
          breathes. */}
      <div className="arena-idle is-player">
        <img className="arena-layer" src={LAYERS.rig} alt="" />
        {/* While he types, his resting pose and the same pose with his hands
            lifted off the keys take turns, so his fingers hammer the keys. */}
        <div className={classes("arena-layer", "arena-keystroke", typing && "is-down")}>
          <img
            ref={playerRef}
            className={classes("arena-layer", "arena-player", playerStruck && "is-striking", enemyStruck && "is-hit", playerHealed && "is-healed")}
            src={LAYERS.player}
            alt="Dr. Chronos"
          />
        </div>
        <img className={classes("arena-layer", "arena-keystroke", "is-lifted", typing && "is-up")} src={LAYERS.playerTyping} alt="" />
        {typing && <span className="arena-keys-flicker" />}
      </div>
      <div className="arena-idle is-enemy">
        <EnemyMonster
          ref={enemyRef}
          className={classes("arena-layer", "arena-enemy", enemyStruck && "is-lunging", playerStruck && "is-hit")}
          name={enemy.name}
          maxHp={enemy.maxHp}
          attack={enemy.attack}
          setting={enemy.setting}
        />
      </div>
      <CombatMonitor lines={log} commands={commands} />
      {exchange && (
        <div key={exchange.id} className="arena-fx" aria-hidden="true">
          {exchange.enemyDelta !== 0 && <DamagePopup side="enemy" delta={exchange.enemyDelta} />}
          {exchange.playerDelta !== 0 && <DamagePopup side="player" delta={exchange.playerDelta} />}
          {playerStruck && (
            <>
              <CablePulse />
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
