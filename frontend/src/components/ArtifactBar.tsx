import type { Artifact } from "../api";
import { ArtifactIcon } from "./ArtifactIcon";

// The installed artifacts. On the map there is room to spell each one out;
// in the combat HUD they shrink to chips with the effect in the tooltip.
export function ArtifactBar({ artifacts, compact = false }: { artifacts: Artifact[]; compact?: boolean }) {
  if (artifacts.length === 0) return null;

  if (compact) {
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
    <section className="artifact-list" aria-label="Artifacts">
      <h2 className="artifact-list-title">Artifacts ({artifacts.length})</h2>
      <ul>
        {artifacts.map((artifact) => (
          <li key={artifact.id} className="artifact-row">
            <span className="artifact-badge">
              <ArtifactIcon id={artifact.id} size={20} />
            </span>
            <span>
              <span className="artifact-name">{artifact.name}</span>
              <span className="artifact-description">{artifact.description}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
