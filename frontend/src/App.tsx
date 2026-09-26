import { useEffect, useState } from "react";
import "./App.css";
import {
  chooseEventOption,
  chooseNextNode,
  createRun,
  endCombatTurn,
  listSettings,
  playCard,
  resolveCurrentNode,
  type PendingCombatView,
  type RunView,
} from "./api";
import { CombatPanel } from "./components/CombatPanel";
import { DungeonMap } from "./components/DungeonMap";
import { EndScreen } from "./components/EndScreen";
import { EventPrompt } from "./components/EventPrompt";
import { HistoryLog } from "./components/HistoryLog";
import { PlayerStats } from "./components/PlayerStats";
import { SettingPicker } from "./components/SettingPicker";

const FALLBACK_SETTINGS = ["dungeon"];

function App() {
  const [run, setRun] = useState<RunView | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<string[]>(FALLBACK_SETTINGS);
  const [selectedSetting, setSelectedSetting] = useState(FALLBACK_SETTINGS[0]);
  const [isMapOpen, setIsMapOpen] = useState(false);
  // The server closes a won fight in the same response as the killing blow.
  // Keep showing that fight - enemy at 0 HP - so the arena can play the enemy's
  // death and wait for the player to move on instead of cutting away at once.
  const [slainCombat, setSlainCombat] = useState<PendingCombatView | null>(null);
  const combat = run?.pending_combat ?? slainCombat;
  const inCombat = Boolean(combat);

  useEffect(() => {
    if (!inCombat) setIsMapOpen(false);
  }, [inCombat]);

  useEffect(() => {
    listSettings()
      .then((fetched) => {
        setSettings(fetched);
        setSelectedSetting(fetched[0]);
      })
      .catch(() => {
        // Keep the dungeon-only fallback - createRun still works either way.
      });
  }, []);

  async function runAction(action: () => Promise<RunView>) {
    setIsLoading(true);
    setError(null);
    try {
      const next = await action();
      const fight = run?.pending_combat;
      setSlainCombat(
        fight && !next.pending_combat && next.player.hp > 0
          ? { ...fight, enemy_hp: 0, enemy_block: 0 }
          : null,
      );
      setRun(next);
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
        <SettingPicker
          settings={settings}
          selected={selectedSetting}
          onSelect={setSelectedSetting}
          disabled={isLoading}
        />
        <button
          disabled={isLoading || selectedSetting.trim() === ""}
          onClick={() => runAction(() => createRun(selectedSetting))}
        >
          Start run
        </button>
        {error && <p className="error">{error}</p>}
      </main>
    );
  }

  const mapProps = {
    nodes: run.nodes,
    currentNodeId: run.current_node.id,
    reachableIds: run.available_choices.map((n) => n.id),
    disabled: isLoading,
    onChoose: (nodeId: string) => runAction(() => chooseNextNode(run.run_id, nodeId)),
  };

  return (
    <main className={`game${inCombat ? " is-wide" : ""}`}>
      <h1>agentic-rogue-like</h1>
      <p className="setting-badge">{run.setting}</p>
      {/* in combat the HUD and the arena monitor show this instead */}
      {!inCombat && <PlayerStats player={run.player} floor={run.floor} />}

      {inCombat ? (
        <div className="map-toggle-row">
          <button
            type="button"
            className="icon-btn"
            aria-label="Show map"
            onClick={() => setIsMapOpen(true)}
          >
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
              <circle className="dial" cx="10" cy="10" r="7" />
              <line className="dial" x1="10" y1="3.6" x2="10" y2="5" />
              <line className="dial" x1="10" y1="15" x2="10" y2="16.4" />
              <line className="dial" x1="3.6" y1="10" x2="5" y2="10" />
              <line className="dial" x1="15" y1="10" x2="16.4" y2="10" />
              <line className="needle" x1="10" y1="10" x2="10" y2="5.6" />
              <line className="needle" x1="10" y1="10" x2="12.6" y2="12.6" />
            </svg>
          </button>
        </div>
      ) : (
        <DungeonMap {...mapProps} />
      )}

      {inCombat && isMapOpen && (
        <div className="map-overlay">
          <div className="map-overlay-panel">
            <div className="map-overlay-head">
              <span>Map</span>
              <button
                type="button"
                className="icon-btn is-small"
                aria-label="Close map"
                onClick={() => setIsMapOpen(false)}
              >
                <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
                  <line className="close-icon" x1="3" y1="3" x2="13" y2="13" />
                  <line className="close-icon" x1="13" y1="3" x2="3" y2="13" />
                </svg>
              </button>
            </div>
            <DungeonMap {...mapProps} />
          </div>
        </div>
      )}

      {!inCombat && <HistoryLog history={run.history} />}
      {error && <p className="error">{error}</p>}

      {run.status !== "ongoing" && !slainCombat && <EndScreen run={run} onRestart={() => setRun(null)} />}

      {run.status === "ongoing" && run.pending_event && (
        <EventPrompt
          event={run.pending_event}
          disabled={isLoading}
          onChoose={(optionIndex) =>
            runAction(() => chooseEventOption(run.run_id, optionIndex))
          }
        />
      )}

      {combat && (run.status === "ongoing" || slainCombat) && (
        <CombatPanel
          combat={combat}
          setting={run.setting}
          player={run.player}
          log={run.history}
          disabled={isLoading || slainCombat !== null}
          enemySlain={slainCombat !== null}
          onContinue={() => setSlainCombat(null)}
          onPlayCard={(handIndex, slotIndex) =>
            runAction(() => playCard(run.run_id, handIndex, slotIndex))
          }
          onEndTurn={() => runAction(() => endCombatTurn(run.run_id))}
        />
      )}

      {run.status === "ongoing" &&
        !run.pending_event &&
        !combat &&
        !run.node_resolved && (
          <button disabled={isLoading} onClick={() => runAction(() => resolveCurrentNode(run.run_id))}>
            Continue
          </button>
        )}

      {run.status === "ongoing" && !slainCombat && run.node_resolved && run.available_choices.length > 0 && (
        <p className="map-hint">Choose your next room on the map above.</p>
      )}
    </main>
  );
}

export default App;
