import type { Artifact } from "../api";
import { ArtifactIcon } from "./ArtifactIcon";

// The installed artifacts. On the map there is room to spell each one out;
// in the combat HUD they shrink to chips with the effect in the tooltip.
export function ArtifactBar({ artifacts, compact = false }: { artifacts: Artifact[]; compact?: boolean }) {
  if (compact) {
    if (artifacts.length === 0) return null;
    return (
      <ul className="artifact-bar" aria-label="Artifacts">
        {artifacts.map((artifact) => (
          <li
            key={artifact.id}
            className="artifact-chip"
            title={`${artifact.name}: ${artifact.description}`}
            tabIndex={0}
          >
            <ArtifactIcon id={artifact.id} size={13} />
            {artifact.name}
          </li>
        ))}
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
        <ul className="artifact-list">
          {artifacts.map((artifact) => (
            <li key={artifact.id}>
              <span className="artifact-badge">
                <ArtifactIcon id={artifact.id} size={18} />
              </span>
              <div>
                <b>{artifact.name}</b>
                <span>{artifact.description}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
