import type { Artifact } from "../api";
import { artifactTimer } from "../artifactTimers";
import { ArtifactIcon } from "./ArtifactIcon";
import { RichText } from "./RichText";

// The installed artifacts. On the map there is room to spell each one out;
// in the combat HUD they shrink to chips with the effect in the tooltip.
// `turn` (in a fight): the artifacts that work every Nth turn light up on
// their turn and count down to it otherwise.
// `pulse` (in a fight): the artifacts that just did something, flashed once
// - `id` tells one flash from the next.
export function ArtifactBar({
  artifacts,
  compact = false,
  turn,
  pulse,
}: {
  artifacts: Artifact[];
  compact?: boolean;
  turn?: number;
  pulse?: { ids: string[]; id: number };
}) {
  if (compact) {
    if (artifacts.length === 0) return null;
    return (
      <ul className="artifact-bar" aria-label="Artifacts">
        {artifacts.map((artifact) => {
          const timer = turn === undefined ? null : artifactTimer(artifact, turn);
          const state = timer
            ? timer.active
              ? ` Active this turn: ${timer.effect}.`
              : ` Next in ${timer.next} turn${timer.next === 1 ? "" : "s"}.`
            : "";
          return (
            <li
              key={pulse?.ids.includes(artifact.id) ? `${artifact.id}-${pulse.id}` : artifact.id}
              className={`artifact-chip${timer ? " is-timed" : ""}${timer?.active ? ` is-firing is-${timer.tone}` : ""}${pulse?.ids.includes(artifact.id) ? " is-pulsed" : ""}`}
              data-artifact-id={artifact.id}
              data-tip-term={artifact.name}
              data-tip={artifact.description + state}
              tabIndex={0}
            >
              <ArtifactIcon id={artifact.id} size={13} />
              {artifact.name}
              {timer && (
                <b className="artifact-timer" aria-label={timer.active ? "active this turn" : `in ${timer.next}`}>
                  {timer.active ? "NOW" : `in ${timer.next}`}
                </b>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section className="panel artifact-panel" aria-label="Artifacts">
      <div className="panel-head">
        <h2 className="panel-title">Artifacts</h2>
        <span className="panel-sub">{artifacts.length} installed</span>
      </div>
      {artifacts.length === 0 ? (
        <p className="muted">None installed yet.</p>
      ) : (
        // relics on a shelf: icon and name; what each does opens over it on
        // hover or focus (the text stays in the item for screen readers)
        <ul className="artifact-list artifact-shelf">
          {artifacts.map((artifact) => (
            <li key={artifact.id} tabIndex={0}>
              <span className="artifact-badge">
                <ArtifactIcon id={artifact.id} size={26} />
              </span>
              <div>
                <b>{artifact.name}</b>
                <span className="artifact-shelf-tip">
                  <RichText text={artifact.description} />
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
