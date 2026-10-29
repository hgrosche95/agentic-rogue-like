import { useEffect, useState } from "react";
import "./App.css";
import "@fontsource/orbitron/500.css";
import "@fontsource/orbitron/700.css";
import "@fontsource/rajdhani/500.css";
import "@fontsource/rajdhani/600.css";
import "@fontsource/rajdhani/700.css";
import "./neon.css";
import {
  buyShopArtifact,
  removeShopCard,
  buyShopCard,
  chooseArtifact,
  chooseCardReward,
  chooseDeal,
  chooseEventOption,
  chooseKit,
  chooseNextNode,
  createRun,
  moveQueued,
  endCombatTurn,
  leaveShop,
  listCharacters,
  listSettings,
  ping,
  getRun,
  playCard,
  resolveCurrentNode,
  restHeal,
  restRemove,
  restUpgrade,
  RequestLostError,
  RunLostError,
  type Character,
  type CharacterView,
  type PendingCombatView,
  type RunView,
} from "./api";
import { FALLBACK_CHARACTERS, ShowTokensContext } from "./characters";
import { music, sfx, type Mood } from "./audio";
import { AgiPanel } from "./components/AgiPanel";
import { ArtifactBar } from "./components/ArtifactBar";
import { ArtifactScreen } from "./components/ArtifactScreen";
import { AudioControls } from "./components/AudioControls";
import { CharacterPicker } from "./components/CharacterPicker";
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
import { OverlayStage } from "./components/OverlayStage";
import { RUN_ID_KEY } from "./errors";
import { layerLabel, numFloorsOf } from "./layers";
import { ProgramModeContext } from "./program";
import { RestScreen } from "./components/RestScreen";
import { RewardScreen } from "./components/RewardScreen";
import { ModePicker } from "./components/ModePicker";
import { SettingPicker } from "./components/SettingPicker";
import { DealScreen, KitScreen } from "./components/StartScreens";
import { ShopScreen } from "./components/ShopScreen";
import { Tooltips } from "./components/RichText";

const FALLBACK_SETTINGS = ["dungeon"];
const INTRO_SEEN_KEY = "agentic-rogue-like:intro-seen";

// well under the container app's 300 s scale-down cooldown
const KEEP_ALIVE_MS = 2 * 60 * 1000;
const KEEP_ALIVE_IDLE_MS = 30 * 60 * 1000;

// The intro plays once per browser; storage can be blocked (private mode),
// and then it simply plays again next time.
function hasSeenIntro(): boolean {
  try {
    return localStorage.getItem(INTRO_SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

// The run in progress (RUN_ID_KEY), so a reload - or a stuck screen - picks
// it up again instead of starting over, as long as the API still has it.
function storedRunId(): string | null {
  try {
    return localStorage.getItem(RUN_ID_KEY);
  } catch {
    return null;
  }
}

function storeRunId(runId: string | null) {
  try {
    if (runId === null) localStorage.removeItem(RUN_ID_KEY);
    else localStorage.setItem(RUN_ID_KEY, runId);
  } catch {
    // Nothing to do - a reload then starts on the title screen.
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
  const [characters, setCharacters] = useState<CharacterView[]>(FALLBACK_CHARACTERS);
  const [selectedCharacter, setSelectedCharacter] = useState<Character>("chronos");
  const [programMode, setProgramMode] = useState(false);
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

  // How far down the AGI's code the run is, 0 at the title screen to 1 at the
  // last core: the page's ground darkens with it (see body in neon.css).
  const depth = run ? (run.act - 1 + run.floor / Math.max(1, numFloorsOf(run.nodes) - 1)) / run.num_acts : 0;
  useEffect(() => {
    document.documentElement.style.setProperty("--depth", depth.toFixed(3));
  }, [depth]);

  useEffect(() => {
    if (!inCombat) setIsMapOpen(false);
  }, [inCombat]);

  // D opens the deck in a fight and closes it again (the other combat keys
  // are CombatPanel's) - not over another window, nor while typing.
  useEffect(() => {
    if (!inCombat) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "d" || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.target instanceof HTMLElement && event.target.closest("input, textarea, select")) return;
      if (!isDeckOpen && document.querySelector(".overlay-backdrop")) return;
      sfx.play("click");
      setIsDeckOpen(!isDeckOpen);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inCombat, isDeckOpen]);

  useEffect(() => {
    listSettings()
      .then((fetched) => {
        setSettings(fetched);
        setSelectedSetting(fetched[0]);
      })
      .catch(() => {
        // Keep the dungeon-only fallback - createRun still works either way.
      });
    listCharacters()
      .then(setCharacters)
      .catch(() => {
        // Keep Dr. Chronos alone - he's the API's default anyway.
      });
  }, []);

  // Keep the API awake while a run is open: runs only live in its memory, and
  // the container scales to zero after 5 idle minutes - reading a card or the
  // map that long used to lose the run. The ping stops once nobody has touched
  // the page for a while, so a forgotten tab doesn't keep the server up.
  const runOpen = run !== null && run.status === "ongoing";
  useEffect(() => {
    if (!runOpen) return;
    let lastActivity = Date.now();
    const touch = () => {
      lastActivity = Date.now();
    };
    const events = ["pointerdown", "keydown", "pointermove"] as const;
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    const timer = window.setInterval(() => {
      if (Date.now() - lastActivity < KEEP_ALIVE_IDLE_MS) ping().catch(() => {});
    }, KEEP_ALIVE_MS);
    return () => {
      window.clearInterval(timer);
      events.forEach((e) => window.removeEventListener(e, touch));
    };
  }, [runOpen]);

  // Pick up the stored run on load; a run the API no longer knows is dropped.
  useEffect(() => {
    const runId = storedRunId();
    if (!runId) return;
    getRun(runId)
      .then((stored) => {
        if (stored.status === "ongoing") setRun((current) => current ?? stored);
        else storeRunId(null);
      })
      .catch(() => storeRunId(null));
  }, []);

  const runId = run !== null && run.status === "ongoing" ? run.run_id : null;
  useEffect(() => {
    // only forget the stored run once one was open here - not on first load
    if (runId !== null) storeRunId(runId);
  }, [runId]);

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
      // nothing left to retry against - back to the title screen
      if (err instanceof RunLostError) {
        setRun(null);
        setSlainCombat(null);
      }
      // The move may have gone through without its answer: take the server's
      // word for where the run stands now.
      if (err instanceof RequestLostError && run !== null) {
        try {
          setRun(await getRun(run.run_id));
          setSlainCombat(null);
        } catch {
          // still unreachable - the error stays up and the next click retries
        }
      }
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
        <Tooltips />
        <AudioControls className="is-floating" />
        <Brand />
        <p className="title-tagline">A deckbuilder: hack your way down into a rogue AGI's code</p>
        <CharacterPicker
          characters={characters}
          selected={selectedCharacter}
          onSelect={(character) => {
            sfx.play("select");
            setSelectedCharacter(character);
          }}
          disabled={isLoading}
        />
        <SettingPicker
          settings={settings}
          selected={selectedSetting}
          onSelect={setSelectedSetting}
          disabled={isLoading}
        />
        <ModePicker
          program={programMode}
          onSelect={(program) => {
            sfx.play("select");
            setProgramMode(program);
          }}
          disabled={isLoading}
        />
        <button
          className="is-primary start-run"
          disabled={isLoading || selectedSetting.trim() === ""}
          onClick={() => {
            sfx.play("select");
            runAction(
              () => createRun(selectedSetting, selectedCharacter, programMode),
              "Building the dungeon...",
            );
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

  function enterRoom() {
    sfx.play("click");
    runAction(
      () => resolveCurrentNode(run!.run_id),
      ["combat", "elite", "boss"].includes(run!.current_node.type) ? "Generating the enemy..." : "Entering the room...",
    );
  }

  const ongoing = run.status === "ongoing";
  const canJump = ongoing && !slainCombat && run.node_resolved && run.available_choices.length > 0;
  const needsEnter =
    ongoing &&
    !run.pending_event &&
    !run.card_reward &&
    !run.artifact_offer &&
    !run.kit_offer &&
    !run.agi_deals &&
    !run.shop &&
    !run.rest &&
    !run.node_resolved;
  // A jump only commits once its room is entered: until then the player can
  // switch to any other room the jump could have gone to.
  const switchChoices = needsEnter ? (run.switch_choices ?? []) : [];

  function jumpTo(nodeId: string) {
    sfx.play("map_select");
    setFocusedJump(null);
    runAction(
      () => chooseNextNode(run!.run_id, nodeId),
      needsEnter ? "Switching rooms..." : "Going one layer deeper...",
    );
  }

  const mapProps = {
    nodes: run.nodes,
    currentNodeId: run.current_node.id,
    reachableIds: (needsEnter ? switchChoices : run.available_choices).map((n) => n.id),
    disabled: isLoading,
    act: run.act,
    onChoose: jumpTo,
  };

  // cards show their token cost only to a character with a context window
  const showTokens = characters.some((c) => c.id === run.player.character && c.token_limit !== null);

  const screen = (
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
          era={layerLabel(run.floor, numFloors, run.act)}
          log={run.history}
          disabled={isLoading || slainCombat !== null}
          enemySlain={slainCombat !== null}
          onContinue={() => setSlainCombat(null)}
          onPlayCard={(handIndex, slotIndex, banish) =>
            runAction(() => playCard(run.run_id, handIndex, slotIndex, banish))
          }
          onEndTurn={(discard) => runAction(() => endCombatTurn(run.run_id, discard))}
          onMoveQueued={(fromSlot, toSlot) => runAction(() => moveQueued(run.run_id, fromSlot, toSlot))}
        />
      ) : (
        <div className="map-layout">
          <section className="panel map-panel">
            <div className="panel-head">
              <h2 className="panel-title">Call stack</h2>
              <span className="panel-sub">
                {canJump
                  ? "Select your next jump"
                  : switchChoices.length > 0
                    ? "Switch rooms until you enter"
                    : run.setting}
              </span>
            </div>
            <DungeonMap {...mapProps} onHover={setFocusedJump} onEnter={needsEnter ? enterRoom : undefined} />
          </section>

          <aside className="map-side">
            <JumpPanel
              current={run.current_node}
              needsEnter={needsEnter}
              choices={run.available_choices}
              switchChoices={switchChoices}
              focusedId={focusedJump}
              numFloors={numFloors}
              act={run.act}
              canJump={canJump}
              disabled={isLoading}
              onEnter={enterRoom}
              onChoose={jumpTo}
            />
            <ArtifactBar artifacts={run.player.artifacts} />
            <AgiPanel style={run.play_style} counts={run.style_counts} />
            <HistoryLog history={run.history} />
          </aside>
        </div>
      )}

      {/* choices open as windows over the map, which stays where it is; the
          stage folds one shut before the next opens */}
      <OverlayStage busy={isLoading}>
      {!combat && !ongoing && (
        <Overlay key="end" label="Run over" className="is-wide">
          <EndScreen run={run} onRestart={() => setRun(null)} />
        </Overlay>
      )}
      {!combat && ongoing && run.pending_event && (
        <Overlay key={`event:${run.pending_event.description}`} label="Anomaly">
          <EventPrompt
            event={run.pending_event}
            disabled={isLoading}
            onChoose={(optionIndex) => runAction(() => chooseEventOption(run.run_id, optionIndex))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.card_reward && !run.artifact_offer && (
        <Overlay key="card" label="Choose a card" className="is-wide">
          <RewardScreen
            offer={run.card_reward}
            deckSize={run.player.deck.length}
            disabled={isLoading}
            onPick={(cardIndex) => runAction(() => chooseCardReward(run.run_id, cardIndex))}
          />
        </Overlay>
      )}
      {/* at the start the artifact comes first, then the kit, then the AGI's deal */}
      {!combat && ongoing && run.kit_offer && !run.artifact_offer && (
        <Overlay key="kit" label="Pack a starter kit" className="is-wide">
          <KitScreen
            offer={run.kit_offer}
            disabled={isLoading}
            onPick={(kitIndex) => runAction(() => chooseKit(run.run_id, kitIndex))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.agi_deals && (
        <Overlay key="deal" label="The AGI's offer" className="is-wide">
          <DealScreen
            deals={run.agi_deals}
            disabled={isLoading}
            onPick={(dealIndex) => runAction(() => chooseDeal(run.run_id, dealIndex))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.shop && (
        <Overlay key="shop" label="Black market" className="is-wide">
          <ShopScreen
            shop={run.shop}
            gold={run.player.gold}
            deck={run.player.deck}
            disabled={isLoading}
            onRemoveCard={(index) => runAction(() => removeShopCard(run.run_id, index))}
            onBuyCard={(index) => runAction(() => buyShopCard(run.run_id, index))}
            onBuyArtifact={(index) => runAction(() => buyShopArtifact(run.run_id, index))}
            onLeave={() => runAction(() => leaveShop(run.run_id))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.rest && (
        <Overlay key="rest" label="Safehouse" className="is-wide">
          <RestScreen
            rest={run.rest}
            hp={run.player.hp}
            maxHp={run.player.max_hp}
            deck={run.player.deck}
            disabled={isLoading}
            onHeal={() => runAction(() => restHeal(run.run_id))}
            onUpgrade={(index) => runAction(() => restUpgrade(run.run_id, index))}
            onRemove={(index) => runAction(() => restRemove(run.run_id, index))}
          />
        </Overlay>
      )}
      {!combat && ongoing && run.artifact_offer && (
        <Overlay key="artifact" label="Choose an artifact" className="is-wide">
          <ArtifactScreen
            offer={run.artifact_offer}
            owned={run.player.artifacts.length}
            disabled={isLoading}
            onPick={(artifactIndex) => runAction(() => chooseArtifact(run.run_id, artifactIndex))}
          />
        </Overlay>
      )}
      </OverlayStage>

      {inCombat && isMapOpen && (
        <Overlay label="Call stack" onClose={() => setIsMapOpen(false)} className="is-wide">
          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Call stack</h2>
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

  return (
    <ShowTokensContext.Provider value={showTokens}>
      <ProgramModeContext.Provider value={run.program_mode}>{screen}</ProgramModeContext.Provider>
      <Tooltips />
    </ShowTokensContext.Provider>
  );
}

export default App;
