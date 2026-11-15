import type { TurnSummary } from "../turnSummary";

// The program's run in one card, over the program board once it has run.
export function TurnSummaryCard({ summary, onClose }: { summary: TurnSummary; onClose: () => void }) {
  return (
    <aside className="turn-summary" role="status" aria-label={`Turn ${summary.turn} summary`}>
      <header>
        <span className="turn-summary-kicker">Turn {summary.turn} · program run</span>
        <button type="button" className="turn-summary-close" aria-label="Close" onClick={onClose}>
          ×
        </button>
      </header>
      <div className="turn-summary-totals">
        <span className="is-damage">
          <b>{summary.dealt}</b> damage
        </span>
        {summary.block > 0 && (
          <span className="is-block">
            <b>+{summary.block}</b> block
          </span>
        )}
      </div>
      <ul>
        {summary.best && summary.best.dealt > 0 && (
          <li>
            Best line: <b>{summary.best.name}</b> {summary.best.dealt}
            {summary.best.runs > 1 && ` (${summary.best.runs}×)`}
          </li>
        )}
        {summary.combos.length > 0 && <li className="is-combo">★ {summary.combos.join(" · ")}</li>}
        {summary.lost > 0 && (
          <li className="is-lost">
            {summary.lost} line{summary.lost === 1 ? "" : "s"} didn't run
          </li>
        )}
        {summary.artifacts && <li className="is-artifact">{summary.artifacts}</li>}
      </ul>
    </aside>
  );
}
