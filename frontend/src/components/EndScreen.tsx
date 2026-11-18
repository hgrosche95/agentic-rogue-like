import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { getVerdict, RunLostError, type DefeatedEnemy, type RunStats, type RunView } from "../api";
import { sfx } from "../audio";
import { HERO } from "../characters";
import { stackDeck } from "../deck";
import { layerLabel, numFloorsOf } from "../layers";
import { enemySprite } from "../pixel/enemySprite";
import { COLORS } from "../pixel/palette";
import { SETTING_LABELS } from "../settings";
import { usePrefersReducedMotion, useTyped } from "../typing";
import { ArtifactIcon } from "./ArtifactIcon";
import { CardFace } from "./CardFace";
import { NodeBadge } from "./DungeonMap";
import { LoadingIndicator } from "./LoadingIndicator";

// How long a tile's number takes to count up, and how far apart the tiles start.
const COUNT_MS = 900;
const STAGGER_MS = 70;
// The verdict is typed at the pace of the intro's AGI message (IntroScreen).
const VERDICT_TYPE_MS = 22;
// How long the seed button says "Copied" after a write went through.
const COPIED_LABEL_MS = 1500;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Milliseconds since the screen opened, ticking until every tile has counted
// up - with reduced motion it starts out finished.
function useElapsed(totalMs: number): number {
  const [elapsed, setElapsed] = useState(() => (prefersReducedMotion() ? totalMs : 0));
  useEffect(() => {
    if (prefersReducedMotion()) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const next = Math.min(totalMs, now - start);
      setElapsed(next);
      if (next < totalMs) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [totalMs]);
  return elapsed;
}

// The value `value` shows `ms` into its count-up, eased out.
function counted(value: number, ms: number): number {
  const t = Math.max(0, Math.min(1, ms / COUNT_MS));
  return Math.round(value * (1 - (1 - t) ** 3));
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m ${String(s).padStart(2, "0")}s`;
}

interface Tile {
  label: string;
  value: number;
  sub?: string;
  tone?: "good" | "bad" | "gold";
}

// HP and attack the *defeated* sprites are drawn from, per tier (stats.TIERS).
// DefeatedEnemy names only the tier, so the look comes from the tier envelopes
// of agent/budgets.py at their midpoints, which cover both the static pool and
// the generated enemies held to it. Values below the sprite's HP_RANGE /
// ATTACK_RANGE clamp to the ranges' lower edges, exactly like the tiers'
// weakest entries do. The boss row never reaches the canvas: its tier selects
// the hand-drawn sprite. The killer does not use this table - it carries the
// HP and attack it actually fought with (KillingBlow) and passes them straight
// to the sprite, so it draws at its real size (enemySprite scales R = 11 +
// hpT * 8 off the HP). Guessing a tier from the HP instead drew it at the
// table's midpoint values and changed its look.
const TIER_STATS: Record<string, { maxHp: number; attack: number }> = {
  early: { maxHp: 36, attack: 8 }, // 32-40 HP / 7-10 attack
  mid: { maxHp: 54, attack: 10 }, // 48-60 / 9-12
  // attack at the envelope's top: elites hit hard enough for the angry brows
  elite: { maxHp: 70, attack: 13 }, // 64-76 / 11-13
  boss: { maxHp: 98, attack: 13 }, // 90-105 / 12-14 - unused, see above
};

// An enemy as a pixel sprite: its name seeds the body, the setting colors it,
// and the run's boss draws hand-made. A defeated row carries no stats of its
// own, so its tier stands for the numbers the fights at it had (TIER_STATS);
// the killer passes the HP and attack it fought with, and real values override
// the tier table completely. A few rows knocked sideways like a frame that
// froze mid-glitch. Drawn at the sprite's own resolution; `scale` multiplies
// --w and --h, which the reused .summary-killer-sprite CSS upscales
// whole-numbered (2px, 3px on wide screens), keeping the pixels crisp; the
// small defeated row scales it back to 1 CSS pixel per sprite pixel instead.
function EnemyPixel({ name, tier, setting, scale, maxHp, attack, finalBoss }: {
  name: string;
  tier?: string;
  setting: string;
  scale: number;
  // the caller's real stats, when it has them (the killer); without them the
  // sprite falls back to the tier's table entry
  maxHp?: number;
  attack?: number;
  finalBoss?: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const sprite = useMemo(() => {
    const tierStats = (tier ? TIER_STATS[tier] : undefined) ?? TIER_STATS.mid;
    return enemySprite({
      name,
      maxHp: maxHp ?? tierStats.maxHp,
      attack: attack ?? tierStats.attack,
      setting,
      finalBoss: finalBoss ?? tier === "boss",
    });
  }, [name, tier, setting, maxHp, attack, finalBoss]);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, sprite.w, sprite.h - sprite.top);
    // its empty rows above the head are cut, so it sits in the frame's middle
    for (let y = sprite.top; y < sprite.h; y++) {
      // three thin bands of the frame slip, as the connection drops
      const slip = y % 23 === 7 ? 2 : y % 31 === 19 ? -3 : 0;
      for (let x = 0; x < sprite.w; x++) {
        const p = sprite.pixels[y * sprite.w + x];
        if (!p) continue;
        ctx.fillStyle = COLORS[p - 1];
        ctx.fillRect(x + slip, y - sprite.top, 1, 1);
      }
    }
  }, [sprite]);
  return (
    <canvas
      ref={ref}
      className="summary-killer-sprite"
      width={sprite.w}
      height={sprite.h - sprite.top}
      style={{ "--w": sprite.w * scale, "--h": (sprite.h - sprite.top) * scale } as CSSProperties}
      aria-hidden="true"
    />
  );
}

// How deep the run got: one segment per layer of the act, lit up to where
// it ended.
function DepthBar({ floor, numFloors, act, numActs }: { floor: number; numFloors: number; act: number; numActs: number }) {
  return (
    <div className="summary-depth" aria-label={`Act ${act} of ${numActs}, layer ${floor + 1} of ${numFloors}`}>
      <span className="summary-depth-label">
        Act {act}/{numActs} · layer <b>{floor + 1}</b>/{numFloors}
      </span>
      <span className="summary-depth-bar" aria-hidden="true">
        {Array.from({ length: numFloors }, (_, i) => (
          <i key={i} className={i < floor ? "is-done" : i === floor ? "is-here" : undefined} />
        ))}
      </span>
    </div>
  );
}

// The live counters, not the summary: `stats` is in every response, so a run
// whose summary was never built still shows what it actually did. Deck and
// credit deltas are left out - the deck and artifact rows below already name
// what the run ended with.
function tilesOf(stats: RunStats): Tile[] {
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return [
    {
      label: "Fights won",
      value: stats.fights_won,
      sub: `${count(stats.elites_defeated, "elite", "elites")} · ${count(stats.bosses_defeated, "boss", "bosses")}`,
    },
    { label: "Turns", value: stats.turns },
    { label: "Damage dealt", value: stats.damage_dealt, tone: "good" },
    { label: "Damage taken", value: stats.damage_taken, tone: "bad" },
    { label: "Biggest hit", value: stats.biggest_hit, tone: "good" },
  ];
}

// The three cards played most, for the "Most played" row: plays from high to
// low, and names A-Z on a tie - without that second key the order would follow
// the order play_counts happened to be built in, which is not a fact about the
// run.
function topPlayed(counts: Record<string, number>): { name: string; count: number }[] {
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([name, count]) => ({ name, count }));
}

// One row per enemy name the run beat, with how often it fell. DefeatedEnemy
// carries no stats of its own, so the sprite is built from the tier the fight
// was scaled for; a name met at two tiers draws as it was met first, because
// the row shows the name once anyway.
function groupDefeated(defeated: DefeatedEnemy[]): { name: string; tier: string; count: number }[] {
  const byName = new Map<string, { name: string; tier: string; count: number }>();
  for (const enemy of defeated) {
    const entry = byName.get(enemy.name);
    if (entry) entry.count += 1;
    else byName.set(enemy.name, { name: enemy.name, tier: enemy.tier, count: 1 });
  }
  return [...byName.values()];
}

export function EndScreen({ run, onRestart, onRunLost }: {
  run: RunView;
  onRestart: () => void;
  // App's shared lost-run path: the verdict fetch is not a runAction, so its
  // 404 cannot reach runAction's catch - it comes up through this callback
  // instead of being thrown in render, where it would land in an error
  // boundary (or hang the whole app without one)
  onRunLost: (err: Error) => void;
}) {
  const won = run.status === "victory";
  useEffect(() => {
    sfx.play(won ? "victory" : "defeat");
  }, [won]);
  // the summary is only read for the duration: a run started before the server
  // kept stats has none, and its chip is then simply left out
  const duration = run.summary?.duration_seconds ?? null;
  const stats = run.stats;
  // a stat that stayed at 0 says nothing - only the fights won always shows
  const tiles = tilesOf(stats).filter((tile, i) => i === 0 || tile.value > 0);
  // only a lost run names an enemy that ended it, and only when a fight did:
  // dying to an event leaves no killer behind, so the block is left out
  const killer = won ? null : stats.killed_by;
  const numFloors = numFloorsOf(run.nodes);
  const elapsed = useElapsed(COUNT_MS + STAGGER_MS * tiles.length);
  const deck = stackDeck(run.player.deck);
  // the rooms of this act entered, in the order of the layers
  const path = Object.values(run.nodes)
    .filter((node) => node.visited || node.id === run.current_node.id)
    .sort((a, b) => a.floor - b.floor);
  const mostPlayed = topPlayed(stats.play_counts);
  const defeated = groupDefeated(stats.defeated);

  // --- the AGI's verdict on this run (GET /runs/{id}/verdict) ---
  const [verdict, setVerdict] = useState<string | null>(null);
  const [verdictPending, setVerdictPending] = useState(true);
  const [verdictRevealed, setVerdictRevealed] = useState(false);
  // fetched exactly once per run: the server makes the text on the first call
  // and keeps it on the session, and this screen re-renders constantly while
  // the tiles count up; the cancel flag also stops a StrictMode remount from
  // firing a second call
  useEffect(() => {
    let cancelled = false;
    getVerdict(run.run_id)
      .then((answer) => {
        if (!cancelled) setVerdict(answer.verdict);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RunLostError) {
          // 404: the server lost this run while it was being read back. Hand
          // it to App's lost-run path - the same one runAction's catch takes.
          // Re-throwing it in render would land in an error boundary, not in
          // that handler.
          onRunLost(err);
          return;
        }
        // 409 (the run is still underway) and every other failure: stay
        // silent - no text, no error screen; a missing verdict beats a wrong
        // one, and none of these say anything about the run itself
      })
      .finally(() => {
        if (!cancelled) setVerdictPending(false);
      });
    return () => {
      cancelled = true;
    };
    // App hands a stable (useCallback) handler, so this stays once per run_id
  }, [run.run_id, onRunLost]);
  const verdictText = verdict ?? "";
  // the intro's typing pace; prefers-reduced-motion shows the whole text at
  // once (checked here, as IntroScreen checks it), and a click on the panel
  // finishes the rest early (as IntroScreen's terminal does)
  const reduced = usePrefersReducedMotion();
  const typedVerdict = useTyped(verdictText, VERDICT_TYPE_MS);
  const shownVerdict = reduced || verdictRevealed ? verdictText.length : typedVerdict;

  // --- seed copy ---
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), COPIED_LABEL_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);
  function copySeed() {
    if (run.seed == null) return;
    // the clipboard API is missing outright in an insecure context (a plain
    // http page served over the LAN): ?. short-circuits the whole call chain,
    // where navigator.clipboard.writeText(...) would throw a synchronous
    // TypeError no .catch could ever reach - the promise is never built.
    // A write that is refused (user denial) rejects instead. Either way the
    // label stays "Copy seed" - claiming "Copied" without the write going
    // through would lie about what the button did.
    navigator.clipboard?.writeText(String(run.seed)).then(() => setCopied(true)).catch(() => {});
  }
  return (
    <div className={`end-screen run-summary ${won ? "is-won" : "is-lost"}`}>
      <header className={`summary-head${killer ? " has-killer" : ""}`}>
        {killer && (
          <div className="summary-killer-frame">
            {/* the killer as it actually stood: its own HP sizes the sprite,
                its own attack shapes spikes and brows */}
            <EnemyPixel
              name={killer.enemy}
              setting={run.setting}
              scale={1}
              maxHp={killer.enemy_max_hp}
              attack={killer.enemy_attack}
              finalBoss={killer.final_boss}
            />
          </div>
        )}
        <div className="summary-head-text">
          <h2>{won ? "Victory" : "Defeat"}</h2>
          {killer && (
            <>
              {/* who ended the run, in the same voice as the headline above it */}
              <p className="summary-killer-line">
                Killed by <b>{killer.enemy}</b>
              </p>
              {/* the name stands in the line above, so the dump adds only what
                  took the last HP: the move, Malware, Thorns... */}
              <p className="summary-dump">
                <span>&gt; last signal: {killer.move}</span>
              </p>
            </>
          )}
          <DepthBar floor={run.floor} numFloors={numFloors} act={run.act} numActs={run.num_acts} />
          <ul className="summary-meta">
            <li>{HERO[run.player.character].name}</li>
            {/* the world the run ran in - a custom one shows as it was typed */}
            <li>{SETTING_LABELS[run.setting] ?? run.setting}</li>
            <li>
              act <b>{run.act}</b>/{run.num_acts} · <b>{layerLabel(run.floor, numFloors, run.act)}</b>
            </li>
            <li>{run.program_mode ? "Program mode" : "Classic mode"}</li>
            {duration != null && <li>{formatDuration(duration)}</li>}
          </ul>
        </div>
      </header>

      <div className={`summary-body${mostPlayed.length > 0 ? " has-highlights" : ""}`}>
        <ul className="summary-tiles" aria-label="Run statistics">
          {tiles.map((tile, i) => (
            <li
              key={tile.label}
              className={`summary-tile${tile.tone ? ` is-${tile.tone}` : ""}`}
              style={{ "--i": i } as CSSProperties}
            >
              <b className="summary-value">{counted(tile.value, elapsed - i * STAGGER_MS).toLocaleString("en-US")}</b>
              <span className="summary-label">{tile.label}</span>
              {tile.sub && <small className="summary-sub">{tile.sub}</small>}
            </li>
          ))}
        </ul>

        {/* the card played most is the row's first entry, so no separate MVP:
            what a card did with its plays is what the row shows */}
        {mostPlayed.length > 0 && (
          <section className="summary-highlight is-played" aria-label="Most played cards">
            <h3>Most played</h3>
            <ol className="summary-played">
              {mostPlayed.map((play) => (
                <li key={play.name}>
                  <span>{play.name}</span>
                  <b>×{play.count}</b>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>

      {/* every enemy the run beat, drawn as the sprite it fought with; the
          ones met more than once stand once, with how often they fell */}
      {defeated.length > 0 && (
        <section className="summary-defeated" aria-label="Enemies defeated">
          <h3>
            Defeated <span>{defeated.length}</span>
          </h3>
          <ul>
            {defeated.map((enemy, i) => (
              <li key={enemy.name} style={{ "--i": i } as CSSProperties} data-tip={enemy.name} tabIndex={0}>
                <EnemyPixel name={enemy.name} tier={enemy.tier} setting={run.setting} scale={0.5} />
                {enemy.count > 1 && <b>×{enemy.count}</b>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* the way taken through this act's call stack, room by room */}
      <section className="summary-path" aria-label="Your path">
        <h3>
          Your path <span>{run.act > 1 ? `act ${run.act} · after ${run.act - 1} cleared` : `act ${run.act}`}</span>
        </h3>
        <ol>
          {path.map((node, i) => (
            <li key={node.id} style={{ "--i": i } as CSSProperties} className={i === path.length - 1 ? "is-last" : undefined}>
              <NodeBadge type={node.type} size={26} />
              <small>{layerLabel(node.floor, numFloorsOf(run.nodes), run.act)}</small>
            </li>
          ))}
        </ol>
      </section>

      {run.player.artifacts.length > 0 && (
        <section className="summary-artifacts" aria-label="Artifacts">
          <h3>
            Artifacts <span>{run.player.artifacts.length}</span>
          </h3>
          <ul>
            {run.player.artifacts.map((artifact, i) => (
              <li key={artifact.id} style={{ "--i": i } as CSSProperties} data-tip-term={artifact.name} data-tip={artifact.description} tabIndex={0}>
                <ArtifactIcon id={artifact.id} size={22} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="summary-deck" aria-label="Final deck">
        <h3>
          Final deck <span>{run.player.deck.length} cards</span>
        </h3>
        {/* the whole deck at a glance: the cards themselves in their hand
            look, shrunk whole-numbered; stacks of copies carry a count badge */}
        <div className="end-deck-row">
          {deck.map(({ card, count }) => (
            <div key={card.name} className={`hand-card type-${card.type}`}>
              <CardFace card={card} />
              {count > 1 && <span className="deck-count">×{count}</span>}
            </div>
          ))}
        </div>
      </section>

      {/* the AGI's closing words on the run, in its terminal look from the
          intro; pending shows the loading toast, a failed call leaves no
          section behind (the catch above already handles 404 and the rest) */}
      {(verdictPending || verdict != null) && (
        <section
          className="summary-verdict"
          aria-label="The AGI's verdict"
          onClick={() => setVerdictRevealed(true)}
        >
          <div className="summary-verdict-head">
            <span>Transmission · AGI</span>
            <i aria-hidden="true" />
          </div>
          {verdict == null ? (
            <LoadingIndicator active label="The AGI is reading the run back" />
          ) : (
            <p aria-live="polite">
              {verdictText.slice(0, shownVerdict)}
              {shownVerdict < verdictText.length && <span className="monitor-cursor" />}
            </p>
          )}
        </section>
      )}

      <div className="end-actions">
        <button
          type="button"
          className="is-primary"
          onClick={() => {
            sfx.play("click");
            onRestart();
          }}
        >Start a new run</button>
        {/* only runs the server answered with a seed can be replayed, and
            only those offer the copy */}
        {run.seed != null && (
          <button type="button" onClick={copySeed}>
            {copied ? "Copied" : "Copy seed"}
          </button>
        )}
      </div>
    </div>
  );
}
