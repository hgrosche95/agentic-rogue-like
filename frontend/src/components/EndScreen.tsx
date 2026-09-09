import type { RunView } from "../api";

export function EndScreen({ run, onRestart }: { run: RunView; onRestart: () => void }) {
  const won = run.status === "victory";
  return (
    <div className="end-screen">
      <h2>{won ? "Victory!" : "You have fallen."}</h2>
      <p>
        Reached floor {run.floor} with {run.player.gold} gold.
      </p>
      <button onClick={onRestart}>Start a new run</button>
    </div>
  );
}
