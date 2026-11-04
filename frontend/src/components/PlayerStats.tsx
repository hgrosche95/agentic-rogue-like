import { useState, type ReactNode } from "react";
import type { PlayerState } from "../api";
import { layerLabel } from "../layers";
import { useCountUp } from "../hooks/useCountUp";
import { PLAYER_HIT_MS, useLagged } from "../hooks/useLagged";

// The credits roll up to a new total instead of jumping there, and what came
// in floats off the counter ("+17") - loot is the moment after a fight.
function Credits({ gold }: { gold: number }) {
  // the total before the last change, kept beside it (see useHpExchange)
  const [last, setLast] = useState({ gold, from: gold });
  if (gold !== last.gold) setLast({ gold, from: last.gold });
  const from = gold !== last.gold ? last.gold : last.from;
  const shown = useCountUp(gold, { from, durationMs: 700, delayMs: 250 });
  const gained = gold - from;
  return (
    <span className="stat-val credits-val">
      {shown}
      {gained > 0 && (
        <span key={gold} className="credits-gain" aria-hidden="true">
          +{gained}
        </span>
      )}
    </span>
  );
}

// The small icons in front of the vitals: a heart that beats when HP
// changes, a blade, a coin that turns over whenever the credits change
// (keyed by the total, so a new one plays its turn).
function StatIcon({ kind, spin = false }: { kind: "hp" | "atk" | "coin"; spin?: boolean }) {
  return (
    <svg className={`stat-icon is-${kind}${spin ? " is-spin" : ""}`} viewBox="0 0 16 16" aria-hidden="true">
      {kind === "hp" && <path d="M8 14 2.4 8.4A3.4 3.4 0 0 1 8 4.2a3.4 3.4 0 0 1 5.6 4.2Z" />}
      {kind === "atk" && <path d="M3 13 11.5 4.5M10 3h3v3M2 11l3 3" />}
      {kind === "coin" && (
        <>
          <circle cx="8" cy="8" r="5.6" />
          <path d="M8 5v6M6.2 6.4h2.6a1.2 1.2 0 0 1 0 2.4H7.2a1.2 1.2 0 0 0 0 2.4h2.6" />
        </>
      )}
    </svg>
  );
}

function BrandGlyph() {
  return (
    <svg className="brand-glyph" viewBox="0 0 32 32" aria-hidden="true">
      {/* a shell prompt, >_ : the way into the AGI's code */}
      <circle cx="16" cy="16" r="13" />
      <path d="M9 10 L16 16 L9 22 V18.6 L12.2 16 L9 13.4 Z M17 19.5 H23.5 V22 H17 Z" />
      <line x1="16" y1="1" x2="16" y2="4" />
      <line x1="16" y1="28" x2="16" y2="31" />
    </svg>
  );
}

export function Brand({ subtitle }: { subtitle?: string }) {
  return (
    <div className="brand">
      <BrandGlyph />
      <div>
        <h1 className="brand-name">
          Agentic<span>//</span>Rogue
        </h1>
        {subtitle && <div className="brand-sub">{subtitle}</div>}
      </div>
    </div>
  );
}

// The run's header: logo, progress down the call stack, the player's vitals
// and the buttons (audio, map) passed in as children.
export function TopBar({
  player,
  floor,
  numFloors,
  act,
  numActs,
  setting,
  children,
}: {
  player: PlayerState;
  floor: number;
  numFloors: number;
  act: number;
  numActs: number;
  setting: string;
  children?: ReactNode;
}) {
  // in a fight the enemy's hit lands a moment after the server's answer
  const hp = useLagged(player.hp, PLAYER_HIT_MS);
  const hpPercent = Math.max(0, Math.min(100, (hp / player.max_hp) * 100));
  return (
    <header className="topbar">
      <Brand subtitle={`Call stack · ${setting}`} />
      <div className="era-track" aria-label={`Act ${act} of ${numActs}, layer ${floor + 1} of ${numFloors}`}>
        {Array.from({ length: numFloors }, (_, i) => (
          <i key={i} className={i < floor ? "is-past" : i === floor ? "is-now" : undefined} />
        ))}
        <span className="era-text">
          Act <b>{act}</b>/{numActs} · Layer <b>{String(floor + 1).padStart(2, "0")}</b>/{String(numFloors).padStart(2, "0")} · {layerLabel(floor, numFloors, act)}
        </span>
      </div>
      <div className="stats">
        <div className="stat stat-hp" title={`${hp}/${player.max_hp} HP`}>
          <span className="stat-label">
            <StatIcon kind="hp" />
            Integrity
          </span>
          <span className="stat-bar">
            <span style={{ width: `${hpPercent}%` }} />
          </span>
          <span className="stat-val">
            {hp}
            <small>/{player.max_hp}</small>
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">
            <StatIcon kind="atk" />
            Atk
          </span>
          <span className="stat-val">{player.attack}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Deck</span>
          <span className="stat-val">{player.deck.length}</span>
        </div>
        <div className="stat stat-gold">
          <span className="stat-label">
            <StatIcon kind="coin" key={player.gold} spin />
            Credits
          </span>
          <Credits gold={player.gold} />
        </div>
        <div className="topbar-buttons">{children}</div>
      </div>
    </header>
  );
}
