import type { PlayStyle } from "../api";

const LABEL: Record<PlayStyle, string> = {
  permanents: "Permanents",
  graveyard: "Cache",
  one_shot: "One-shots",
  aggro: "Attacks",
  turtle: "Blocking",
  malware: "Malware",
  program: "Control flow",
};

// What the AGI has read from the cards the player chose (style.py): once one
// style clearly leads, enemies and elite affixes start to answer it.
export function AgiPanel({
  style,
  counts,
}: {
  style: PlayStyle | null;
  counts: Partial<Record<PlayStyle, number>>;
}) {
  const ranked = (Object.entries(counts) as [PlayStyle, number][])
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  return (
    <section className="panel agi-panel" aria-label="AGI analysis">
      <div className="panel-head">
        <h2 className="panel-title">AGI analysis</h2>
        {/* the AGI's eye on the player: a recording light */}
        <span className="panel-sub agi-rec">{style ? "adapting" : "watching"}</span>
      </div>
      <p className="muted">
        {style
          ? `Your deck leans on ${LABEL[style].toLowerCase()} - expect enemies that answer it.`
          : "No clear pattern in the cards you chose yet."}
      </p>
      {ranked.length > 0 && (
        <ul className="agi-counts">
          {ranked.map(([s, n]) => (
            <li
              key={s}
              className={s === style ? "is-lead" : ""}
              tabIndex={0}
              data-tip-term={LABEL[s]}
              data-tip={`${n} of the cards you picked play this way. Once one way clearly leads, the AGI sends enemies that answer it.`}
            >
              {LABEL[s]} <b>{n}</b>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
