import type { MapNode } from "../api";
import { eraLabel } from "../eras";
import { NODE_STYLE } from "../nodeTypes";
import { NodeBadge } from "./DungeonMap";

// The side column's first panel - always in the same place, so the map never
// moves: before a room is entered it offers to enter it, afterwards it
// previews the next jump (the room under the pointer, else the first route).
// Jumping itself is one click, on the map or on the button here.
export function JumpPanel({
  current,
  needsEnter,
  choices,
  focusedId,
  numFloors,
  act,
  canJump,
  disabled,
  onEnter,
  onChoose,
}: {
  current: MapNode;
  needsEnter: boolean;
  choices: MapNode[];
  focusedId: string | null;
  numFloors: number;
  act: number;
  canJump: boolean;
  disabled: boolean;
  onEnter: () => void;
  onChoose: (nodeId: string) => void;
}) {
  if (needsEnter) {
    const room = NODE_STYLE[current.type];
    return (
      <section className="panel jump-panel is-arrived">
        <div className="panel-head">
          <h2 className="panel-title">Arrived</h2>
          <span className="panel-sub">{eraLabel(current.floor, numFloors, act)}</span>
        </div>
        <div className="jump-target">
          <NodeBadge type={current.type} size={40} />
          <div>
            <b>{room.label}</b>
            <span>{room.blurb}</span>
          </div>
        </div>
        <button type="button" className="is-primary jump-button" disabled={disabled} onClick={onEnter}>
          {["combat", "elite", "boss"].includes(current.type) ? "Engage" : "Enter"}
        </button>
      </section>
    );
  }

  const target = choices.find((n) => n.id === focusedId) ?? choices[0];
  return (
    <section className="panel jump-panel">
      <div className="panel-head">
        <h2 className="panel-title">Next jump</h2>
        {target && canJump && <span className="panel-sub">{eraLabel(target.floor, numFloors, act)}</span>}
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
            <em>{choices.length === 1 ? "1 route" : `${choices.length} routes`} · click a room to jump</em>
          </div>
          <button
            type="button"
            className="is-primary jump-button"
            disabled={disabled}
            onClick={() => onChoose(target.id)}
          >
            Initiate jump
          </button>
        </>
      ) : (
        <p className="muted">{canJump ? "No route leads further." : "Finish this era before you jump."}</p>
      )}
    </section>
  );
}
