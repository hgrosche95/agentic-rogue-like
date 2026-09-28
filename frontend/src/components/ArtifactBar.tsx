import type { Artifact } from "../api";

// The installed artifacts as small chips; the effect is in the tooltip.
export function ArtifactBar({ artifacts }: { artifacts: Artifact[] }) {
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
