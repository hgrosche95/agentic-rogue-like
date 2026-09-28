import type { MapNode } from "../api";
import { eraLabel } from "../eras";
import { NODE_STYLE } from "../nodeTypes";
import { NodeBadge } from "./DungeonMap";

// What the next jump leads to: the room selected on the map, else the one
// under the pointer, else the first one on offer. The button jumps there -
// the confirm step after selecting a room on the map.
export function JumpPanel({
  choices,
  plannedId,
  focusedId,
  numFloors,
  canJump,
  disabled,
  onChoose,
  onCancel,
}: {
  choices: MapNode[];
  plannedId: string | null;
  focusedId: string | null;
  numFloors: number;
  canJump: boolean;
  disabled: boolean;
  onChoose: (nodeId: string) => void;
  onCancel: () => void;
}) {
  const target =
    choices.find((n) => n.id === plannedId) ?? choices.find((n) => n.id === focusedId) ?? choices[0];
  const isPlanned = target !== undefined && target.id === plannedId;
  return (
    <section className={`panel jump-panel${isPlanned ? " is-planned" : ""}`}>
      <div className="panel-head">
        <h2 className="panel-title">Next jump</h2>
        {target && canJump && (
          <span className="panel-sub">
            {isPlanned ? "Selected · " : ""}
            {eraLabel(target.floor, numFloors)}
          </span>
        )}
      </div>
      {target && canJump ? (
        <>
          <div className="jump-target">
            <NodeBadge type={target.type} size={40} />
            <div>
              <b>{NODE_STYLE[target.type].label}</b>
              <span>{NODE_STYLE[target.type].blurb}</span>
            </div>
          </div>
          <div className="jump-options">
            {choices.map((n) => (
              <span key={n.id} className={n.id === target.id ? "is-focused" : undefined}>
                <NodeBadge type={n.type} size={18} />
              </span>
            ))}
            <em>{isPlanned ? "click the room again to go" : choices.length === 1 ? "1 route" : `${choices.length} routes`}</em>
          </div>
          <div className="jump-actions">
            <button type="button" className="is-primary" disabled={disabled} onClick={() => onChoose(target.id)}>
              Initiate jump
            </button>
            {isPlanned && (
              <button type="button" disabled={disabled} onClick={onCancel}>
                Cancel
              </button>
            )}
          </div>
        </>
      ) : (
        <p className="muted">{canJump ? "No route leads further." : "Finish this era before you jump."}</p>
      )}
    </section>
  );
}
