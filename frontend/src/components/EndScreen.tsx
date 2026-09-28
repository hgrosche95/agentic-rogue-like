import { useEffect } from "react";
import type { RunView } from "../api";
import { sfx } from "../audio";

export function EndScreen({ run, onRestart }: { run: RunView; onRestart: () => void }) {
  const won = run.status === "victory";
  useEffect(() => {
    sfx.play(won ? "victory" : "defeat");
  }, [won]);
  return (
    <div className={`end-screen ${won ? "is-won" : "is-lost"}`}>
      <h2>{won ? "Victory!" : "You have fallen."}</h2>
      <p>
        Reached floor {run.floor} with {run.player.gold} gold.
      </p>
      <button
        className="is-primary"
        onClick={() => {
          sfx.play("click");
          onRestart();
        }}
      >Start a new run</button>
    </div>
  );
}
