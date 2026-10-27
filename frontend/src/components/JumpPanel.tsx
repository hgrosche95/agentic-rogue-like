import type { MapNode } from "../api";
import { layerLabel } from "../layers";
import { NODE_STYLE } from "../nodeTypes";
import { NodeBadge } from "./DungeonMap";

// The side column's first panel - always in the same place, so the map never
// moves: before a room is entered it offers to enter it (or to switch to
// another room the jump could have gone to), afterwards it previews the next
// jump (the room under the pointer, else the first route). Jumping itself is
// one click, on the map or on the button here.
export function JumpPanel({
  current,
  needsEnter,
  choices,
  switchChoices,
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
  switchChoices: MapNode[];
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
    // in map order, so the row reads like the layer it picks from
    const rooms = [current, ...switchChoices].sort((a, b) => a.id.localeCompare(b.id, "en", { numeric: true }));
    return (
      <section className="panel jump-panel is-arrived">
        <div className="panel-head">
          <h2 className="panel-title">{switchChoices.length > 0 ? "Jump target" : "Arrived"}</h2>
          <span className="panel-sub">{layerLabel(current.floor, numFloors, act)}</span>
        </div>
        {/* keyed by room: switching slides the new one in */}
        <div key={current.id} className="jump-target is-picked">
          <NodeBadge type={current.type} size={40} />
          <div>
            <b>{room.label}</b>
            <span>{room.blurb}</span>
          </div>
        </div>
        {switchChoices.length > 0 && (
          <div className="jump-options">
            {rooms.map((n) =>
              n.id === current.id ? (
                <span key={n.id} className="is-focused">
                  <NodeBadge type={n.type} size={18} />
                </span>
              ) : (
                <button
                  key={n.id}
                  type="button"
                  className="jump-option"
                  disabled={disabled}
                  aria-label={`Switch to ${NODE_STYLE[n.type].label}`}
                  title={`Switch to ${NODE_STYLE[n.type].label}`}
                  onClick={() => onChoose(n.id)}
                >
                  <NodeBadge type={n.type} size={18} />
                </button>
              ),
            )}
            <em>switch rooms until you enter</em>
          </div>
        )}
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
        {target && canJump && <span className="panel-sub">{layerLabel(target.floor, numFloors, act)}</span>}
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
        <p className="muted">{canJump ? "No route leads further." : "Clear this layer before you go deeper."}</p>
      )}
    </section>
  );
}
