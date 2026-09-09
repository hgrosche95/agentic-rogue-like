import type { PlayerState } from "../api";

export function PlayerStats({ player, floor }: { player: PlayerState; floor: number }) {
  const hpPercent = Math.max(0, Math.min(100, (player.hp / player.max_hp) * 100));

  return (
    <div className="player-stats">
      <span className="stat-floor">Floor {floor}</span>
      <span className="hp-track" title={`${player.hp}/${player.max_hp} HP`}>
        <span className="hp-fill" style={{ width: `${hpPercent}%` }} />
      </span>
      <span className="stat-figure">{player.hp}/{player.max_hp}</span>
      <span className="stat-figure">{player.attack} atk</span>
      <span className="stat-gold">{player.gold} gold</span>
    </div>
  );
}
