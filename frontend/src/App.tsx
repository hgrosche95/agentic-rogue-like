import { useEffect, useState } from "react";
import "./App.css";
import {
  chooseArtifact,
  chooseCardReward,
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
import { music, sfx, type Mood } from "./audio";
import { ArtifactBar } from "./components/ArtifactBar";
import { ArtifactScreen } from "./components/ArtifactScreen";
import { AudioControls } from "./components/AudioControls";
import { CombatPanel } from "./components/CombatPanel";
import { DungeonMap } from "./components/DungeonMap";
import { EndScreen } from "./components/EndScreen";
import { EventPrompt } from "./components/EventPrompt";
import { HistoryLog } from "./components/HistoryLog";
import { IntroScreen } from "./components/IntroScreen";
import { LoadingIndicator } from "./components/LoadingIndicator";
import { PlayerStats } from "./components/PlayerStats";
import { RewardScreen } from "./components/RewardScreen";
import { SettingPicker } from "./components/SettingPicker";
import { NODE_STYLE } from "./nodeTypes";

const FALLBACK_SETTINGS = ["dungeon"];
const INTRO_SEEN_KEY = "agentic-rogue-like:intro-seen";

// The intro plays once per browser; storage can be blocked (private mode),
// and then it simply plays again next time.
function hasSeenIntro(): boolean {
  try {
    return localStorage.getItem(INTRO_SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

function rememberIntroSeen() {
  try {
    localStorage.setItem(INTRO_SEEN_KEY, "1");
  } catch {
    // Nothing to do - see hasSeenIntro.
  }
}

function App() {
  const [run, setRun] = useState<RunView | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Loading...");
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<string[]>(FALLBACK_SETTINGS);
  const [selectedSetting, setSelectedSetting] = useState(FALLBACK_SETTINGS[0]);
  const [isMapOpen, setIsMapOpen] = useState(false);
  // Clicking a room on the map only selects it; moving there needs a confirm,
  // so a misclick can't send the player down the wrong path.
  const [plannedNodeId, setPlannedNodeId] = useState<string | null>(null);
  const [isIntroOpen, setIsIntroOpen] = useState(() => !hasSeenIntro());
  // The server closes a won fight in the same response as the killing blow.
  // Keep showing that fight - enemy at 0 HP - so the arena can play the enemy's
  // death and wait for the player to move on instead of cutting away at once.
  const [slainCombat, setSlainCombat] = useState<PendingCombatView | null>(null);
  const combat = run?.pending_combat ?? slainCombat;
  const inCombat = Boolean(combat);
  const mood: Mood =
    run?.status === "defeat"
      ? "silence"
      : inCombat
        ? run?.current_node.type === "boss"
          ? "boss"
          : "combat"
        : "map";

  useEffect(() => {
    music.setMood(mood);
  }, [mood]);

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

  async function runAction(action: () => Promise<RunView>, label = "Loading...") {
    setLoadingLabel(label);
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
      sfx.play("error");
    } finally {
      setIsLoading(false);
    }
  }

  if (run === null && isIntroOpen) {
    return (
      <main className="game">
        <AudioControls className="is-floating" />
        <IntroScreen
          onDone={() => {
            rememberIntroSeen();
            setIsIntroOpen(false);
          }}
        />
      </main>
    );
  }

  if (run === null) {
    return (
      <main className="game is-title">
        <AudioControls className="is-floating" />
        <h1>agentic-rogue-like</h1>
        <p className="title-tagline">A deckbuilding roguelike, dealt by an AI</p>
        <SettingPicker
          settings={settings}
          selected={selectedSetting}
          onSelect={setSelectedSetting}
          disabled={isLoading}
        />
        <button
          className="is-primary start-run"
          disabled={isLoading || selectedSetting.trim() === ""}
          onClick={() => {
            sfx.play("select");
            runAction(() => createRun(selectedSetting), "Building the dungeon...");
          }}
        >
          Start run
        </button>
        {error && <p className="error">{error}</p>}
        <LoadingIndicator active={isLoading} label={loadingLabel} />
        <button type="button" className="replay-intro" disabled={isLoading} onClick={() => setIsIntroOpen(true)}>
          Replay intro
        </button>
      </main>
    );
  }

  // Only a room that is still reachable counts as planned - after moving
  // on (or any other state change) a stale selection simply drops out.
  const planned = run.available_choices.find((n) => n.id === plannedNodeId) ?? null;

  function confirmMove(nodeId: string) {
    sfx.play("map_select");
    setPlannedNodeId(null);
    runAction(() => chooseNextNode(run!.run_id, nodeId), "Moving on...");
  }

  const mapProps = {
    nodes: run.nodes,
    currentNodeId: run.current_node.id,
    reachableIds: run.available_choices.map((n) => n.id),
    selectedId: planned?.id ?? null,
    disabled: isLoading,
    onChoose: (nodeId: string) => {
      // A second click on the selected room confirms it.
      if (nodeId === planned?.id) return confirmMove(nodeId);
      sfx.play("select");
      setPlannedNodeId(nodeId);
    },
  };

  return (
    <main className={`game${inCombat ? " is-wide" : ""}`}>
      {!inCombat && <AudioControls className="is-floating" />}
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
            onClick={() => {
              sfx.play("click");
              setIsMapOpen(true);
            }}
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
          <AudioControls />
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
      <LoadingIndicator active={isLoading} label={loadingLabel} />
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
          onEndTurn={(discard) => runAction(() => endCombatTurn(run.run_id, discard))}
        />
      )}

      {run.status === "ongoing" && !combat && run.card_reward && (
        <RewardScreen
          offer={run.card_reward}
          deckSize={run.player.deck.length}
          disabled={isLoading}
          onPick={(cardIndex) => runAction(() => chooseCardReward(run.run_id, cardIndex))}
        />
      )}

      {run.status === "ongoing" && !combat && run.artifact_offer && (
        <ArtifactScreen
          offer={run.artifact_offer}
          owned={run.player.artifacts.length}
          disabled={isLoading}
          onPick={(artifactIndex) => runAction(() => chooseArtifact(run.run_id, artifactIndex))}
        />
      )}

      {run.status === "ongoing" &&
        !run.pending_event &&
        !combat &&
        !run.card_reward &&
        !run.artifact_offer &&
        !run.node_resolved && (
          <button
            className="is-primary"
            disabled={isLoading}
            onClick={() => {
              sfx.play("click");
              runAction(
                () => resolveCurrentNode(run.run_id),
                ["combat", "elite", "boss"].includes(run.current_node.type)
                  ? "Generating the enemy..."
                  : "Entering the room...",
              );
            }}
          >
            Continue
          </button>
        )}

      {run.status === "ongoing" && !slainCombat && run.node_resolved && run.available_choices.length > 0 &&
        (planned ? (
          <div className="path-confirm">
            <span>
              Go to <strong>{NODE_STYLE[planned.type].label}</strong> on floor {planned.floor}?
            </span>
            <button disabled={isLoading} onClick={() => confirmMove(planned.id)}>
              Go
            </button>
            <button className="is-secondary" disabled={isLoading} onClick={() => setPlannedNodeId(null)}>
              Cancel
            </button>
          </div>
        ) : (
          <p className="map-hint">Choose your next room on the map above.</p>
        ))}

      {!inCombat && <ArtifactBar artifacts={run.player.artifacts} />}
    </main>
  );
}

export default App;
