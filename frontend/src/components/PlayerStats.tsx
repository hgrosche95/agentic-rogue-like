import type { PlayerState } from "../api";

export function PlayerStats({ player, floor }: { player: PlayerState; floor: number }) {
  return (
    <div className="player-stats">
      <span>Floor {floor}</span>
      <span>
        HP {player.hp}/{player.max_hp}
      </span>
      <span>ATK {player.attack}</span>
      <span>{player.gold} gold</span>
    </div>
  );
}
