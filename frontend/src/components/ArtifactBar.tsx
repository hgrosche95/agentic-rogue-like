import type { Artifact } from "../api";

// The installed artifacts: small chips (effect in the tooltip) in the combat
// HUD, or a list with the effect spelled out on the map screen.
export function ArtifactBar({ artifacts, variant = "chips" }: { artifacts: Artifact[]; variant?: "chips" | "list" }) {
  if (variant === "list") {
    return (
      <section className="panel artifact-panel">
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
                <i aria-hidden="true" />
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
  if (artifacts.length === 0) return null;
  return (
    <ul className="artifact-bar" aria-label="Artifacts">
      {artifacts.map((artifact) => (
        <li key={artifact.id} className="artifact-chip" title={artifact.description} tabIndex={0}>
          {artifact.name}
        </li>
      ))}
    </ul>
  );
}
