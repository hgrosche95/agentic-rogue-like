import type { MapNode } from "../api";
import { eraLabel } from "../eras";
import { NODE_STYLE } from "../nodeTypes";
import { NodeBadge } from "./DungeonMap";

// What the next jump leads to: the room under the pointer on the map, else
// the first one on offer. The button jumps there, the same as clicking it.
export function JumpPanel({
  choices,
  focusedId,
  numFloors,
  canJump,
  disabled,
  onChoose,
}: {
  choices: MapNode[];
  focusedId: string | null;
  numFloors: number;
  canJump: boolean;
  disabled: boolean;
  onChoose: (nodeId: string) => void;
}) {
  const target = choices.find((n) => n.id === focusedId) ?? choices[0];
  return (
    <section className="panel jump-panel">
      <div className="panel-head">
        <h2 className="panel-title">Next jump</h2>
        {target && canJump && <span className="panel-sub">{eraLabel(target.floor, numFloors)}</span>}
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
            <em>{choices.length === 1 ? "1 route" : `${choices.length} routes`}</em>
          </div>
          <button type="button" className="is-primary" disabled={disabled} onClick={() => onChoose(target.id)}>
            Initiate jump
          </button>
        </>
      ) : (
        <p className="muted">{canJump ? "No route leads further." : "Finish this era before you jump."}</p>
      )}
    </section>
  );
}
