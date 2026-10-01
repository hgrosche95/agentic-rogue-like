import { useEffect, useState } from "react";
import "./App.css";
import {
  buyShopArtifact,
  buyShopCard,
  chooseArtifact,
  chooseCardReward,
  chooseEventOption,
  chooseNextNode,
  createRun,
  endCombatTurn,
  leaveShop,
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
import { DeckButton, DeckView } from "./components/DeckView";
import { DungeonMap } from "./components/DungeonMap";
import { EndScreen } from "./components/EndScreen";
import { EventPrompt } from "./components/EventPrompt";
import { HistoryLog } from "./components/HistoryLog";
import { IntroScreen } from "./components/IntroScreen";
import { LoadingIndicator } from "./components/LoadingIndicator";
import { Brand, TopBar } from "./components/PlayerStats";
import { JumpPanel } from "./components/JumpPanel";
import { CloseButton, Overlay } from "./components/Overlay";
import { eraLabel, numFloorsOf } from "./eras";
import { RewardScreen } from "./components/RewardScreen";
import { SettingPicker } from "./components/SettingPicker";
import { ShopScreen } from "./components/ShopScreen";

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
  // Hovering a room on the map previews it in the next-jump panel.
  const [focusedJump, setFocusedJump] = useState<string | null>(null);
  const [isDeckOpen, setIsDeckOpen] = useState(false);
  const [isIntroOpen, setIsIntroOpen] = useState(() => !hasSeenIntro());
  // The server closes a won fight in the same response as the killing blow.
  // Keep showing that fight - enemy at 0 HP - so the arena can play the enemy's
  // death and wait for the player to move on instead of cutting away at once.
  const [slainCombat, setSlainCombat] = useState<PendingCombatView | null>(null);
  const combat = run?.pending_combat ?? slainCombat;
  const inCombat = Boolean(combat);
  // Entering or leaving a fight plays a jump through the rift (see
  // .rift-transition); the id restarts it on every switch.
  const [wasInCombat, setWasInCombat] = useState(inCombat);
  const [riftJump, setRiftJump] = useState(0);
  if (inCombat !== wasInCombat) {
    setWasInCombat(inCombat);
    setRiftJump(riftJump + 1);
  }
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
        <Brand />
        <p className="title-tagline">A time-travel deckbuilder against a rogue AGI</p>
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
        {error && <p className="error toast">{error}</p>}
        <LoadingIndicator active={isLoading} label={loadingLabel} />
        <button type="button" className="link-button replay-intro" disabled={isLoading} onClick={() => setIsIntroOpen(true)}>
          Replay intro
        </button>
      </main>
    );
  }

  const numFloors = numFloorsOf(run.nodes);

  function jumpTo(nodeId: string) {
    sfx.play("map_select");
    setFocusedJump(null);
    runAction(() => chooseNextNode(run!.run_id, nodeId), "Jumping through time...");
  }

  function enterRoom() {
    sfx.play("click");
    runAction(
      () => resolveCurrentNode(run!.run_id),
      ["combat", "elite", "boss"].includes(run!.current_node.type) ? "Generating the enemy..." : "Entering the room...",
    );
  }

  const mapProps = {
    nodes: run.nodes,
    currentNodeId: run.current_node.id,
    reachableIds: run.available_choices.map((n) => n.id),
    disabled: isLoading,
    act: run.act,
    onChoose: jumpTo,
  };
  const ongoing = run.status === "ongoing";
  const canJump = ongoing && !slainCombat && run.node_resolved && run.available_choices.length > 0;
  const needsEnter =
    ongoing &&
    !run.pending_event &&
    !run.card_reward &&
    !run.artifact_offer &&
    !run.shop &&
    !run.node_resolved;

  return (
    <main className={`game${inCombat ? " is-combat" : ""}`}>
      <TopBar
        player={run.player}
        floor={run.floor}
        numFloors={numFloors}
        act={run.act}
        numActs={run.num_acts}
        setting={run.setting}
      >
        <DeckButton
          count={run.player.deck.length}
          onClick={() => {
            sfx.play("click");
            setIsDeckOpen(true);
          }}
        />
        {inCombat && (
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
        )}
        <AudioControls />
      </TopBar>

      {combat && (ongoing || slainCombat) ? (
        <CombatPanel
          combat={combat}
          setting={run.setting}
          player={run.player}
          era={eraLabel(run.floor, numFloors, run.act)}
          log={run.history}
          disabled={isLoading || slainCombat !== null}
          enemySlain={slainCombat !== null}
          onContinue={() => setSlainCombat(null)}
          onPlayCard={(handIndex, slotIndex) =>
            runAction(() => playCard(run.run_id, handIndex, slotIndex))
          }
          onEndTurn={(discard) => runAction(() => endCombatTurn(run.run_id, discard))}
        />
      ) : (
        <div className="map-layout">
          <section className="panel map-panel">
            <div className="panel-head">
              <h2 className="panel-title">Temporal map</h2>
              <span className="panel-sub">{canJump ? "Select your next jump" : run.setting}</span>
            </div>
            <DungeonMap {...mapProps} onHover={setFocusedJump} />
          </section>

          <aside className="map-side">
            <JumpPanel
              current={run.current_node}
              needsEnter={needsEnter}
              choices={run.available_choices}
              focusedId={focusedJump}
              numFloors={numFloors}
              act={run.act}
              canJump={canJump}
              disabled={isLoading}
              onEnter={enterRoom}
              onChoose={jumpTo}
            />
            <ArtifactBar artifacts={run.player.artifacts} />
            <HistoryLog history={run.history} />
          </aside>
        </div>
      )}

      {/* choices open as windows over the map, which stays where it is */}
      {!combat && !ongoing && (
        <Overlay label="Run over">
          <EndScreen run={run} onRestart={() => setRun(null)} />
        </Overlay>
      )}
      {!combat && ongoing && run.pending_event && (
        <Overlay label="Anomaly">
          <EventPrompt
            event={run.pending_event}
            disabled={isLoading}
            onChoose={(optionIndex) => runAction(() => chooseEventOption(run.run_id, optionIndex))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.card_reward && (
        <Overlay label="Choose a card" className="is-wide">
          <RewardScreen
            offer={run.card_reward}
            deckSize={run.player.deck.length}
            disabled={isLoading}
            onPick={(cardIndex) => runAction(() => chooseCardReward(run.run_id, cardIndex))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.shop && (
        <Overlay label="Black market" className="is-wide">
          <ShopScreen
            shop={run.shop}
            gold={run.player.gold}
            disabled={isLoading}
            onBuyCard={(index) => runAction(() => buyShopCard(run.run_id, index))}
            onBuyArtifact={(index) => runAction(() => buyShopArtifact(run.run_id, index))}
            onLeave={() => runAction(() => leaveShop(run.run_id))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.artifact_offer && (
        <Overlay label="Choose an artifact" className="is-wide">
          <ArtifactScreen
            offer={run.artifact_offer}
            owned={run.player.artifacts.length}
            disabled={isLoading}
            onPick={(artifactIndex) => runAction(() => chooseArtifact(run.run_id, artifactIndex))}
          />
        </Overlay>
      )}

      {inCombat && isMapOpen && (
        <Overlay label="Temporal map" onClose={() => setIsMapOpen(false)} className="is-wide">
          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Temporal map</h2>
              <CloseButton onClick={() => setIsMapOpen(false)} label="Close map" />
            </div>
            <DungeonMap {...mapProps} />
          </section>
        </Overlay>
      )}
      {isDeckOpen && <DeckView deck={run.player.deck} onClose={() => setIsDeckOpen(false)} />}

      {riftJump > 0 && (
        <div key={riftJump} className={`rift-transition ${inCombat ? "is-enter" : "is-exit"}`} aria-hidden="true" />
      )}
      <LoadingIndicator active={isLoading} label={loadingLabel} />
      {error && <p className="error toast">{error}</p>}
    </main>
  );
}

export default App;
