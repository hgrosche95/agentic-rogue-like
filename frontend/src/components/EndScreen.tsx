import { useEffect, useState, type CSSProperties } from "react";
import type { RunSummary, RunView } from "../api";
import { sfx } from "../audio";
import { HERO } from "../characters";
import { stackDeck } from "../deck";
import { layerLabel, numFloorsOf } from "../layers";
import { CardFace } from "./CardFace";

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
  const tiles = summary ? tilesOf(summary) : [];
  const elapsed = useElapsed(COUNT_MS + STAGGER_MS * tiles.length);
  const layer = layerLabel(run.floor, numFloorsOf(run.nodes), run.act);
  const deck = stackDeck(run.player.deck);
  const combo = summary?.best_combo ?? null;
  const highlights = summary !== null && (summary.killed_by !== null || combo !== null || summary.mvp_card !== null);

  return (
    <div className={`end-screen run-summary ${won ? "is-won" : "is-lost"}`}>
      <header className="summary-head">
        <span className="summary-kicker">{won ? "Run complete" : "Connection lost"}</span>
        <h2>{won ? "Victory" : "You have fallen"}</h2>
        <ul className="summary-meta">
          <li>
            Act {run.act}/{run.num_acts} · <b>{layer}</b>
          </li>
          <li>{HERO[run.player.character].name}</li>
          <li>{run.program_mode ? "Program mode" : "Classic mode"}</li>
          {summary?.duration_seconds != null && <li>{formatDuration(summary.duration_seconds)}</li>}
        </ul>
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
              {summary.killed_by && (
                <section className="summary-highlight is-killer">
                  <h3>Killed by</h3>
                  <p className="summary-killer">{summary.killed_by.enemy}</p>
                  <p className="summary-note">with {summary.killed_by.move}</p>
                </section>
              )}
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
          Reached act {run.act}/{run.num_acts}, floor {run.floor + 1} with {run.player.gold} gold.
        </p>
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
