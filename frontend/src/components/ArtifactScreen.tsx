import { useEffect } from "react";
import type { Artifact } from "../api";
import { sfx } from "../audio";
import { pickClass, useOverlayPick } from "../overlayStage";
import { ArtifactIcon } from "./ArtifactIcon";
import { RichText } from "./RichText";

export function ArtifactScreen({
  offer,
  owned,
  disabled,
  onPick,
}: {
  offer: Artifact[];
  owned: number;
  disabled: boolean;
  onPick: (artifactIndex: number) => void;
}) {
  const { picked, pick } = useOverlayPick();
  useEffect(() => {
    sfx.play("reward_open");
  }, []);

  return (
    <div className="reward-screen artifact-screen">
      <h2>Choose an artifact</h2>
      <p className="reward-hint">
        {owned === 0
          ? "Pick one to take into the run - it works passively until the end."
          : `A new artifact every few rooms. You have ${owned} installed.`}
      </p>
      <div className="artifact-offer">
        {offer.map((artifact, index) => (
          <button
            key={artifact.id}
            className={`artifact-card${pickClass(picked, index)}`}
            style={{ animationDelay: `${index * 90}ms` }}
            disabled={disabled}
            onMouseEnter={() => sfx.play("hover")}
            onClick={() => {
              sfx.play("reward_pick");
              pick(index);
              onPick(index);
            }}
          >
            <span className="artifact-badge is-large">
              <ArtifactIcon id={artifact.id} size={30} />
            </span>
            <span className="artifact-name">{artifact.name}</span>
            <span className="artifact-description">
              <RichText text={artifact.description} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
