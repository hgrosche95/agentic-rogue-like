import { useState } from "react";
import "./App.css";
import {
  chooseEventOption,
  chooseNextNode,
  createRun,
  resolveCurrentNode,
  type RunView,
} from "./api";
import { DungeonMap } from "./components/DungeonMap";
import { EndScreen } from "./components/EndScreen";
import { EventPrompt } from "./components/EventPrompt";
import { HistoryLog } from "./components/HistoryLog";
import { PlayerStats } from "./components/PlayerStats";

function App() {
  const [run, setRun] = useState<RunView | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runAction(action: () => Promise<RunView>) {
    setIsLoading(true);
    setError(null);
    try {
      setRun(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }

  if (run === null) {
    return (
      <main className="game">
        <h1>agentic-rogue-like</h1>
        <button disabled={isLoading} onClick={() => runAction(() => createRun())}>
          Start run
        </button>
        {error && <p className="error">{error}</p>}
      </main>
    );
  }

  return (
    <main className="game">
      <h1>agentic-rogue-like</h1>
      <PlayerStats player={run.player} floor={run.floor} />

      <DungeonMap
        nodes={run.nodes}
        currentNodeId={run.current_node.id}
        reachableIds={run.available_choices.map((n) => n.id)}
        disabled={isLoading}
        onChoose={(nodeId) => runAction(() => chooseNextNode(run.run_id, nodeId))}
      />

      <HistoryLog history={run.history} />
      {error && <p className="error">{error}</p>}

      {run.status !== "ongoing" && (
        <EndScreen run={run} onRestart={() => runAction(() => createRun())} />
      )}

      {run.status === "ongoing" && run.pending_event && (
        <EventPrompt
          event={run.pending_event}
          disabled={isLoading}
          onChoose={(optionIndex) =>
            runAction(() => chooseEventOption(run.run_id, optionIndex))
          }
        />
      )}

      {run.status === "ongoing" && !run.pending_event && !run.node_resolved && (
        <button disabled={isLoading} onClick={() => runAction(() => resolveCurrentNode(run.run_id))}>
          Continue
        </button>
      )}

      {run.status === "ongoing" && run.node_resolved && run.available_choices.length > 0 && (
        <p className="map-hint">Choose your next room on the map above.</p>
      )}
    </main>
  );
}

export default App;
