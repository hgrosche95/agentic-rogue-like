import { useCallback, useEffect, useImperativeHandle, useRef, type ReactNode, type Ref } from "react";
import type { CardType } from "../api";
import { sfx } from "../audio";
import type { HackerCommand } from "../hackerCommands";
import type { HpExchange } from "../hooks/useHpExchange";
import { ENEMY_HIT_MS, PLAYER_HIT_MS } from "../hooks/useLagged";
import { enemySprite } from "../pixel/enemySprite";
import { ENEMY_X, FLOOR, PLAYER_X, pct } from "../pixel/layout";
import type { PixelScene } from "../pixel/scene";
import { rangeText } from "../readouts";
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
  intent: "attack" | "defend";
  intentMin: number;
  intentMax: number;
}

export interface ArenaStatus {
  block: number;
  armor: number;
  enemyBlock: number;
  turrets: number;
  amplifiers: number;
  fortify: number;
}

// What CombatPanel tells the arena as things happen; HP changes it works out
// itself from `exchange`.
export interface ArenaHandle {
  // Enter was hit on a played card
  cardPlayed(type: CardType, value: number): void;
  // the server answered an end of turn
  enemyTurn(turn: { attacked: boolean; blocked: boolean; braced: boolean; daemon: boolean }): void;
}

// a blade for an attack, a shield for bracing
export function IntentIcon({ intent }: { intent: "attack" | "defend" }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="intent-icon">
      {intent === "attack" ? (
        <>
          <path className="fill" d="M16.8 2.2 17.8 3.2 9.2 11.8 8.2 10.8Z" />
          <path d="M5.6 10.4 9.6 14.4M7.6 12.4 3.4 16.6" />
        </>
      ) : (
        <path className="fill" d="M10 2.5 L16 5 V9.5 C16 13.5 13.2 16.3 10 17.5 C6.8 16.3 4 13.5 4 9.5 V5 Z" />
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
  const attacking = enemy.intent === "attack";
  const amount = rangeText(enemy.intentMin, enemy.intentMax);
  return (
    <div
      className={`arena-intent is-${enemy.intent}`}
      style={{ left: pct.x(ENEMY_X), top: pct.y(enemyTop(enemy) - 2) }}
      title={attacking ? `Attacks next for ${amount}` : `Braces for ${amount} block next`}
    >
      <IntentIcon intent={enemy.intent} />
      <b>{amount}</b>
    </div>
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
  children?: ReactNode;
  ref?: Ref<ArenaHandle>;
}) {
  const sceneRef = useRef<PixelScene | null>(null);
  const onScene = useCallback((scene: PixelScene) => {
    sceneRef.current = scene;
  }, []);

  const { name, maxHp, attack, setting } = enemy;
  useEffect(() => {
    sceneRef.current?.setEnemy({ name, maxHp, attack, setting });
  }, [name, maxHp, attack, setting]);

  const { block, armor, enemyBlock, turrets, amplifiers, fortify } = status;
  useEffect(() => {
    sceneRef.current?.setStatus({ typing, block, armor, enemyBlock, turrets, amplifiers, fortify });
  }, [typing, block, armor, enemyBlock, turrets, amplifiers, fortify]);

  useImperativeHandle(ref, () => ({
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

  // hits land with the animations, like the HP bars (hooks/useLagged)
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
    sfx.play("enemy_defeated", { delayMs: ENEMY_HIT_MS + 150 });
  }, [slain]);

  const top = enemyTop(enemy);

  return (
    <div className="arena-stage">
      <PixelStage onScene={onScene}>
        {!slain && <IntentMarker key={`${enemy.intent}-${enemy.intentMin}-${enemy.intentMax}`} enemy={enemy} />}
        <CombatMonitor lines={log} commands={commands} />
        {exchange && (
          <div key={exchange.id} className="arena-fx" aria-hidden="true">
            {exchange.enemyDelta !== 0 && <DamagePopup side="enemy" delta={exchange.enemyDelta} top={top - 6} />}
            {exchange.playerDelta !== 0 && <DamagePopup side="player" delta={exchange.playerDelta} top={FLOOR - 48} />}
          </div>
        )}
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
