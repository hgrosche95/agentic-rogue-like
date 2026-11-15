import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { RunSummary, RunView } from "../api";
import { sfx } from "../audio";
import { HERO } from "../characters";
import { stackDeck } from "../deck";
import { layerLabel, numFloorsOf } from "../layers";
import { enemySprite } from "../pixel/enemySprite";
import { COLORS } from "../pixel/palette";
import { ArtifactIcon } from "./ArtifactIcon";
import { CardFace } from "./CardFace";
import { NodeBadge } from "./DungeonMap";

// How long a tile's number takes to count up, and how far apart the tiles start.
const COUNT_MS = 900;
const STAGGER_MS = 70;

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

// The enemy that ended the run, as it stood in the fight: its sprite drawn
// crisp at a whole-number scale, a few rows knocked sideways like a frame
// that froze mid-glitch.
function KillerSprite({ name, maxHp, attack, setting, finalBoss }: {
  name: string;
  maxHp: number;
  attack: number;
  setting: string;
  finalBoss: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const sprite = useMemo(
    () => enemySprite({ name, maxHp, attack, setting, finalBoss }),
    [name, maxHp, attack, setting, finalBoss],
  );
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
      style={{ "--w": sprite.w, "--h": sprite.h - sprite.top } as CSSProperties}
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

function tilesOf(summary: RunSummary): Tile[] {
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return [
    {
      label: "Fights won",
      value: summary.fights_won,
      sub: `${count(summary.elites_defeated, "elite", "elites")} · ${count(summary.bosses_defeated, "boss", "bosses")}`,
    },
    { label: "Damage dealt", value: summary.damage_dealt, tone: "good" },
    { label: "Biggest hit", value: summary.biggest_hit, tone: "good" },
    { label: "Damage taken", value: summary.damage_taken, tone: "bad" },
    { label: "Turns", value: summary.turns },
    { label: "Cards played", value: summary.cards_played },
    {
      label: "Cards added",
      value: summary.cards_added,
      sub: `${summary.cards_removed} removed · ${summary.cards_upgraded} upgraded`,
    },
    {
      label: "Credits earned",
      value: summary.credits_earned,
      sub: `${summary.credits_spent} spent`,
      tone: "gold",
    },
    { label: "Artifacts", value: summary.artifacts_collected },
  ];
}

export function EndScreen({ run, onRestart }: { run: RunView; onRestart: () => void }) {
  const won = run.status === "victory";
  useEffect(() => {
    sfx.play(won ? "victory" : "defeat");
  }, [won]);
  const summary = run.summary;
  // a stat that stayed at 0 says nothing - only the fights won always shows
  const tiles = summary ? tilesOf(summary).filter((tile, i) => i === 0 || tile.value > 0) : [];
  const killer = !won ? (summary?.killed_by ?? null) : null;
  const numFloors = numFloorsOf(run.nodes);
  const elapsed = useElapsed(COUNT_MS + STAGGER_MS * tiles.length);
  const deck = stackDeck(run.player.deck);
  // the rooms of this act entered, in the order of the layers
  const path = Object.values(run.nodes)
    .filter((node) => node.visited || node.id === run.current_node.id)
    .sort((a, b) => a.floor - b.floor);
  const combo = summary?.best_combo ?? null;
  const highlights = summary !== null && (combo !== null || summary.mvp_card !== null);

  return (
    <div className={`end-screen run-summary ${won ? "is-won" : "is-lost"}`}>
      <header className={`summary-head${killer ? " has-killer" : ""}`}>
        {killer && (
          <div className="summary-killer-frame">
            <KillerSprite
              name={killer.enemy}
              maxHp={killer.enemy_max_hp}
              attack={killer.enemy_attack}
              setting={run.setting}
              finalBoss={killer.final_boss}
            />
          </div>
        )}
        <div className="summary-head-text">
          <h2>{won ? "Victory" : "You have fallen"}</h2>
          {killer && (
            <p className="summary-dump">
              <span>&gt; process terminated by <b>{killer.enemy}</b></span>
              <span>&gt; last signal: {killer.move}</span>
            </p>
          )}
          <DepthBar floor={run.floor} numFloors={numFloors} act={run.act} numActs={run.num_acts} />
          <ul className="summary-meta">
            <li>{HERO[run.player.character].name}</li>
            <li>{run.program_mode ? "Program mode" : "Classic mode"}</li>
            {summary?.duration_seconds != null && <li>{formatDuration(summary.duration_seconds)}</li>}
          </ul>
        </div>
      </header>

      {summary && (
        <div className={`summary-body${highlights ? " has-highlights" : ""}`}>
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

          {highlights && (
            <div className="summary-highlights">
              {combo && (
                <section className="summary-highlight is-combo">
                  <h3>Best combo</h3>
                  <p className="summary-combo">
                    <b>{combo.damage}</b> damage
                    <span>
                      {" "}
                      · {combo.runs} {run.program_mode ? "actions run" : "cards played"}
                    </span>
                  </p>
                  <ol className="summary-chain">
                    {combo.cards.map((name, i) => (
                      <li key={i}>
                        <span>{name}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {summary.mvp_card && (
                <section className="summary-highlight is-mvp">
                  <h3>MVP card</h3>
                  <div className="summary-mvp">
                    <div className={`hand-card summary-mvp-card type-${summary.mvp_card.type}`}>
                      <CardFace card={summary.mvp_card} />
                    </div>
                    <p className="summary-note">
                      played <b>{summary.mvp_plays}×</b>
                      <br />
                      {Math.round((100 * summary.mvp_plays) / Math.max(1, summary.cards_played))}% of your plays
                    </p>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      )}

      {!summary && (
        <p>
          Reached act {run.act}/{run.num_acts}, layer {run.floor + 1} with {run.player.gold} credits.
        </p>
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

      <section className="summary-deck">
        <h3>
          Final deck <span>{run.player.deck.length} cards</span>
        </h3>
        <ul>
          {deck.map(({ card, count }) => (
            <li key={card.name} className={`type-${card.type}`}>
              {card.name}
              {count > 1 && <b>×{count}</b>}
            </li>
          ))}
        </ul>
      </section>

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
