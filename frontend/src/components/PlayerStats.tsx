import type { ReactNode } from "react";
import type { PlayerState } from "../api";
import { eraLabel } from "../eras";

function BrandGlyph() {
  return (
    <svg className="brand-glyph" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="13" />
      <path d="M11 8 H21 L16 16 L21 24 H11 L16 16 Z" />
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

// The run's header: logo, progress along the timeline, the player's vitals
// and the buttons (audio, map) passed in as children.
export function TopBar({
  player,
  floor,
  numFloors,
  setting,
  children,
}: {
  player: PlayerState;
  floor: number;
  numFloors: number;
  setting: string;
  children?: ReactNode;
}) {
  const hpPercent = Math.max(0, Math.min(100, (player.hp / player.max_hp) * 100));
  return (
    <header className="topbar">
      <Brand subtitle={`Timeline · ${setting}`} />
      <div className="era-track" aria-label={`Era ${floor + 1} of ${numFloors}`}>
        {Array.from({ length: numFloors }, (_, i) => (
          <i key={i} className={i < floor ? "is-past" : i === floor ? "is-now" : undefined} />
        ))}
        <span className="era-text">
          Era <b>{String(floor + 1).padStart(2, "0")}</b>/{String(numFloors).padStart(2, "0")} · {eraLabel(floor, numFloors)}
        </span>
      </div>
      <div className="stats">
        <div className="stat stat-hp" title={`${player.hp}/${player.max_hp} HP`}>
          <span className="stat-label">Integrity</span>
          <span className="stat-bar">
            <span style={{ width: `${hpPercent}%` }} />
          </span>
          <span className="stat-val">
            {player.hp}
            <small>/{player.max_hp}</small>
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Atk</span>
          <span className="stat-val">{player.attack}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Deck</span>
          <span className="stat-val">{player.deck.length}</span>
        </div>
        <div className="stat stat-gold">
          <span className="stat-label">Credits</span>
          <span className="stat-val">{player.gold}</span>
        </div>
        <div className="topbar-buttons">{children}</div>
      </div>
    </header>
  );
}
