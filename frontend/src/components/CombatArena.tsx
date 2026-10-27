import { useCallback, useEffect, useImperativeHandle, useRef, useState, type ReactNode, type Ref } from "react";
import { ATTACKING_INTENTS, type CardType, type EnemyIntentType } from "../api";
import { sfx } from "../audio";
import type { HackerCommand } from "../hackerCommands";
import type { HpExchange } from "../hooks/useHpExchange";
import { ENEMY_HIT_MS, PLAYER_HIT_MS } from "../hooks/useLagged";
import { enemySprite } from "../pixel/enemySprite";
import { FINAL_BOSS_INTENT_X } from "../pixel/finalBoss";
import { ENEMY_X, FLOOR, PLAYER_X, pct } from "../pixel/layout";
import type { Hero, PixelScene } from "../pixel/scene";
import { describeIntent } from "../readouts";
import { tempoMs } from "../tempo";
import { CombatMonitor } from "./CombatMonitor";
import { PixelStage } from "./PixelStage";

// The combat arena is a pixel-art scene drawn procedurally on a canvas (see
// pixel/scene.ts): Dr. Chronos at his keyboard in the lab, the rift, and the
// enemy - LLM-generated, so its sprite is built from its stats at runtime.
// Every card type has its own animation there. HTML only sits on top where
// text has to stay crisp: the combat log in the monitor, the enemy's intent,
// damage numbers and the victory prompt.

export interface ArenaEnemy {
  name: string;
  maxHp: number;
  attack: number;
  setting: string;
  // what it does next - shown above its head
  intent: EnemyIntentType;
  intentMin: number;
  intentMax: number;
  intentHits: number;
  intentName: string | null;
  // the run's final boss (hand-drawn), and the boss phase it is in
  finalBoss?: boolean;
  phase?: number;
}

export interface ArenaStatus {
  block: number;
  armor: number;
  enemyBlock: number;
  turrets: number;
  amplifiers: number;
  fortify: number;
}

// One program line landing (CombatPanel plays a program out line by line,
// from the preview's steps): what it did, and how heavy it was - the share of
// the enemy's HP it took.
export interface ProgramHit {
  dealt: number;
  runs: number;
  block: number;
  heal: number;
  weight: number;
  // an interrupt cut the program off here
  cut?: boolean;
}

// What CombatPanel tells the arena as things happen; HP changes it works out
// itself from `exchange`.
export interface ArenaHandle {
  // a program line ran (or was cut off)
  programHit(hit: ProgramHit): void;
  // Enter was hit on a played card
  cardPlayed(type: CardType, value: number): void;
  // the server answered an end of turn
  enemyTurn(turn: { attacked: boolean; blocked: boolean; braced: boolean; daemon: boolean }): void;
}

// a blade for an attack, a shield for bracing - and a mark for each boss move
export function IntentIcon({ intent }: { intent: EnemyIntentType }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="intent-icon">
      {intent === "attack" && (
        <>
          <path className="fill" d="M16.8 2.2 17.8 3.2 9.2 11.8 8.2 10.8Z" />
          <path d="M5.6 10.4 9.6 14.4M7.6 12.4 3.4 16.6" />
        </>
      )}
      {intent === "defend" && (
        <path className="fill" d="M10 2.5 L16 5 V9.5 C16 13.5 13.2 16.3 10 17.5 C6.8 16.3 4 13.5 4 9.5 V5 Z" />
      )}
      {intent === "barrage" && <path d="M3 15 8 5M8.5 15 13.5 5M14 15 19 5" />}
      {intent === "charge" && <path className="fill" d="M11.5 1.8 4.5 11h4.6l-1.6 7.2L15.5 9h-4.7Z" />}
      {intent === "overload" && (
        <path
          className="fill"
          d="M10 1.5 12 7.2 18 6.5 13.6 10.6 16.6 16.5 10.8 13.6 7.6 18.5 7.3 12.5 1.8 10.6 7 8.3 5 3Z"
        />
      )}
      {intent === "infect" && (
        <>
          <circle className="fill" cx="10" cy="10" r="2.6" />
          <circle cx="10" cy="4.2" r="2.2" />
          <circle cx="4.9" cy="13" r="2.2" />
          <circle cx="15.1" cy="13" r="2.2" />
        </>
      )}
      {intent === "lock" && (
        <>
          <rect className="fill" x="4.5" y="9" width="11" height="8.5" />
          <path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
        </>
      )}
      {intent === "corrupt" && <path d="M2.5 6h4l2 4h3l2-4h4M2.5 14h4l2-4M11.5 10l2 4h4" />}
      {intent === "refactor" && (
        // two arrows turning back on each other
        <path d="M3 7h12l-3-3M17 13H5l3 3" />
      )}
      {intent === "interrupt" && (
        // a line of code, slashed through
        <path d="M2.5 10h5M12.5 10h5M7 16.5 13 3.5" />
      )}
      {intent === "purge" && (
        <>
          <rect x="3.5" y="3.5" width="13" height="13" rx="2" />
          <path d="M7 7 13 13M13 7 7 13" />
        </>
      )}
    </svg>
  );
}

// the top of the enemy's sprite, in logical pixels
function enemyTop(enemy: ArenaEnemy): number {
  const sprite = enemySprite(enemy);
  return FLOOR - sprite.h + sprite.top;
}

// The enemy's telegraphed next move, floating over its head - the first
// thing a turn is planned around, so it is the loudest mark in the scene.
function IntentMarker({ enemy }: { enemy: ArenaEnemy }) {
  const { amount, title } = describeIntent(
    enemy.intent,
    enemy.intentMin,
    enemy.intentMax,
    enemy.intentHits,
    enemy.intentName,
  );
  const kind = ATTACKING_INTENTS.includes(enemy.intent) ? "is-hit" : "is-guard";
  return (
    <div
      className={`arena-intent ${kind} is-${enemy.intent}`}
      style={{ left: pct.x(enemy.finalBoss ? FINAL_BOSS_INTENT_X : ENEMY_X), top: pct.y(enemyTop(enemy) - 2) }}
      title={title}
    >
      <IntentIcon intent={enemy.intent} />
      <b>{amount}</b>
    </div>
  );
}

// A number a program line put up: damage over the enemy, block or healing
// over Dr. Chronos, the fork/loop multiplier, or the interrupt's cut.
interface ProgramFx {
  id: number;
  kind: "damage" | "combo" | "block" | "heal" | "cut";
  text: string;
  // how many of its kind are up already - they stack instead of overlapping
  stack: number;
}

const PROGRAM_FX_MS = 1100;

// Numbers on Dr. Chronos' side go on his body, like the enemy's on its own:
// over his head they would float up into the HUD plate hanging there.
const PLAYER_FX_TOP = FLOOR - 34;

function ProgramFxPopup({ fx, enemyTop }: { fx: ProgramFx; enemyTop: number }) {
  if (fx.kind === "cut") {
    return <span className="arena-cut">{fx.text}</span>;
  }
  const onEnemy = fx.kind === "damage" || fx.kind === "combo";
  // on the enemy's body, clear of the intent marker over its head
  const top = onEnemy ? enemyTop + 14 - (fx.kind === "combo" ? 14 : 0) - fx.stack * 9 : PLAYER_FX_TOP - fx.stack * 9;
  return (
    <span
      className={`arena-popup arena-program-fx is-${fx.kind}`}
      style={{ left: pct.x(onEnemy ? ENEMY_X : PLAYER_X), top: pct.y(top) }}
    >
      {fx.text}
    </span>
  );
}

function DamagePopup({ side, delta, top }: { side: "player" | "enemy"; delta: number; top: number }) {
  const isHeal = delta > 0;
  return (
    <span
      className={`arena-popup is-${side} ${isHeal ? "is-heal" : "is-damage"}`}
      style={{ left: pct.x(side === "player" ? PLAYER_X : ENEMY_X), top: pct.y(top) }}
    >
      {isHeal ? `+${delta}` : delta}
    </span>
  );
}

export function CombatArena({
  enemy,
  status,
  exchange,
  log,
  commands,
  typing,
  slain = false,
  onContinue,
  hero = "chronos",
  contextFull = false,
  children,
  ref,
}: {
  enemy: ArenaEnemy;
  status: ArenaStatus;
  exchange: HpExchange | null;
  log: string[];
  commands: HackerCommand[];
  typing: boolean;
  slain?: boolean;
  onContinue?: () => void;
  // who stands at the keyboard, and whether the Vibe-Coder's window is full
  hero?: Hero;
  contextFull?: boolean;
  children?: ReactNode;
  ref?: Ref<ArenaHandle>;
}) {
  const sceneRef = useRef<PixelScene | null>(null);
  const [programFx, setProgramFx] = useState<ProgramFx[]>([]);
  const fxId = useRef(0);
  const showFx = useCallback((kind: ProgramFx["kind"], text: string) => {
    const id = ++fxId.current;
    setProgramFx((shown) => [
      ...shown,
      { id, kind, text, stack: shown.filter((f) => f.kind === kind).length },
    ]);
    window.setTimeout(() => setProgramFx((shown) => shown.filter((f) => f.id !== id)), PROGRAM_FX_MS);
  }, []);
  const onScene = useCallback((scene: PixelScene) => {
    sceneRef.current = scene;
  }, []);

  useEffect(() => {
    sceneRef.current?.setHero(hero);
  }, [hero]);

  useEffect(() => {
    sceneRef.current?.setContextFull(contextFull);
  }, [contextFull]);

  const { name, maxHp, attack, setting, finalBoss, phase = 1 } = enemy;
  useEffect(() => {
    sceneRef.current?.setEnemy({ name, maxHp, attack, setting, finalBoss });
  }, [name, maxHp, attack, setting, finalBoss]);
  useEffect(() => {
    sceneRef.current?.setEnemyPhase(phase);
  }, [phase]);

  const { block, armor, enemyBlock, turrets, amplifiers, fortify } = status;
  useEffect(() => {
    sceneRef.current?.setStatus({ typing, block, armor, enemyBlock, turrets, amplifiers, fortify });
  }, [typing, block, armor, enemyBlock, turrets, amplifiers, fortify]);

  useImperativeHandle(ref, () => ({
    programHit(hit) {
      const scene = sceneRef.current;
      if (hit.cut) {
        showFx("cut", "Interrupt");
        scene?.trigger("enemy_brace");
        return;
      }
      if (hit.block > 0) showFx("block", `+${hit.block}`);
      if (hit.heal > 0) showFx("heal", `+${hit.heal}`);
      if (hit.dealt <= 0) return;
      // as the line's pulse comes out of the rift
      window.setTimeout(() => {
        scene?.trigger("enemy_hurt");
        scene?.impact(hit.weight);
        sfx.play("impact");
        showFx("damage", `-${hit.dealt}`);
        if (hit.runs > 1) showFx("combo", `×${hit.runs}`);
      }, tempoMs(ENEMY_HIT_MS));
    },
    cardPlayed(type, value) {
      sceneRef.current?.trigger(type, 0, value);
    },
    enemyTurn({ attacked, blocked, braced, daemon }) {
      const scene = sceneRef.current;
      if (!scene) return;
      if (daemon) scene.trigger("daemon");
      if (attacked) scene.trigger(blocked ? "enemy_attack_blocked" : "enemy_attack");
      if (braced) scene.trigger("enemy_brace");
    },
  }));

  // hits land with the animations, like the HP bars (hooks/useLagged) - the
  // scene counts its delays in its own time, which already follows the tempo
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !exchange) return;
    if (exchange.enemyDelta < 0) scene.trigger("enemy_hurt", ENEMY_HIT_MS);
    if (exchange.playerDelta < 0) scene.trigger("player_hurt", PLAYER_HIT_MS);
    if (exchange.playerDelta > 0) scene.trigger("player_healed", 350);
  }, [exchange]);

  // The enemy comes apart once the killing blow has landed.
  useEffect(() => {
    if (!slain) return;
    sceneRef.current?.trigger("enemy_die", ENEMY_HIT_MS + 150);
    sfx.play("enemy_defeated", { delayMs: tempoMs(ENEMY_HIT_MS + 150) });
  }, [slain]);

  const top = enemyTop(enemy);

  return (
    <div className="arena-stage">
      <PixelStage onScene={onScene} followTempo>
        {!slain && <IntentMarker key={`${enemy.intent}-${enemy.intentMin}-${enemy.intentMax}`} enemy={enemy} />}
        <CombatMonitor lines={log} commands={commands} />
        {exchange && (
          <div key={exchange.id} className="arena-fx" aria-hidden="true">
            {exchange.enemyDelta !== 0 && <DamagePopup side="enemy" delta={exchange.enemyDelta} top={top - 6} />}
            {exchange.playerDelta !== 0 && <DamagePopup side="player" delta={exchange.playerDelta} top={PLAYER_FX_TOP} />}
          </div>
        )}
        {programFx.map((fx) => (
          <ProgramFxPopup key={fx.id} fx={fx} enemyTop={top} />
        ))}
        {children}
        {slain && (
          <div className="arena-victory">
            <span className="arena-victory-title">{enemy.name} defeated</span>
            <button
              type="button"
              className="is-primary arena-continue"
              onClick={() => {
                sfx.play("click");
                onContinue?.();
              }}
            >
              Continue
            </button>
          </div>
        )}
      </PixelStage>
    </div>
  );
}
