import { useEffect, useMemo, useState } from "react";
import type { MapNode, NodeType } from "../api";
import { sfx } from "../audio";
import { NODE_STYLE } from "../nodeTypes";

// Bergpfad on narrow screens: floors climb bottom-to-top, siblings spread
// left-right - a vertical ascent the player scrolls through. On wide
// (desktop) screens the same graph lies down sideways instead - floors run
// left-to-right - so it fits the viewport without scrolling.
const VERTICAL = { SIBLING_W: 68, FLOOR_H: 78, PAD: 40 };
const HORIZONTAL = { FLOOR_W: 94, SIBLING_H: 62, PAD: 46 };
const HORIZONTAL_QUERY = "(min-width: 900px)";
const NODE_R = 15;
const BOSS_R = 21;

function useIsHorizontal(): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(HORIZONTAL_QUERY).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(HORIZONTAL_QUERY);
    const onChange = () => setMatches(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return matches;
}

function nodeIndex(id: string): number {
  return Number(id.split("-")[1]);
}

// The icon on a node's coin, drawn in a 16x16 box around the origin. Shapes
// rather than dingbat/emoji glyphs, so the color stays controllable per node
// state - see the comment in nodeTypes.ts.
export function NodeIcon({ type }: { type: NodeType }) {
  switch (type) {
    case "combat":
      return (
        <g className="node-icon is-stroke">
          <line x1="-6" y1="6" x2="5.5" y2="-5.5" />
          <line x1="6" y1="6" x2="-5.5" y2="-5.5" />
          <line x1="-6.5" y1="2" x2="-2" y2="6.5" />
          <line x1="6.5" y1="2" x2="2" y2="6.5" />
        </g>
      );
    case "elite":
      return (
        <g className="node-icon">
          <path d="M-6 1.5 a6 6 0 1 1 12 0 v1.8 h-2 v2.9 h-8 v-2.9 h-2 z" />
          <circle className="node-icon-hole" cx="-2.4" cy="0.6" r="1.8" />
          <circle className="node-icon-hole" cx="2.4" cy="0.6" r="1.8" />
        </g>
      );
    case "rest":
      return (
        <g className="node-icon">
          <path d="M0 -7.5 C4.5 -3 5.5 0.5 3.4 3.4 C2 5.2 -2 5.2 -3.4 3.4 C-5.4 0.6 -3.2 -2 -1.6 -3.2 C-1.2 -1.6 -0.4 -0.8 0.6 -0.6 C-0.2 -3 0 -5.2 0 -7.5 Z" />
          <line className="node-icon-log" x1="-5.5" y1="6.2" x2="5.5" y2="4.6" />
        </g>
      );
    case "boss":
      return (
        <g className="node-icon is-crown">
          <path d="M-8 4.5 L-8.5 -4.5 L-4 -0.5 L0 -7 L4 -0.5 L8.5 -4.5 L8 4.5 Z" />
          <circle className="node-icon-hole" cx="0" cy="1.6" r="1.6" />
        </g>
      );
    default:
      return <text className="node-icon-text">{NODE_STYLE[type].symbol}</text>;
  }
}

// A trail between two rooms: a gentle S-curve along the direction the floors run.
function trail(from: { x: number; y: number }, to: { x: number; y: number }, horizontal: boolean): string {
  if (horizontal) {
    const mx = (from.x + to.x) / 2;
    return `M ${from.x} ${from.y} C ${mx} ${from.y}, ${mx} ${to.y}, ${to.x} ${to.y}`;
  }
  const my = (from.y + to.y) / 2;
  return `M ${from.x} ${from.y} C ${from.x} ${my}, ${to.x} ${my}, ${to.x} ${to.y}`;
}

export function DungeonMap({
  nodes,
  currentNodeId,
  reachableIds,
  onChoose,
  disabled,
}: {
  nodes: Record<string, MapNode>;
  currentNodeId: string;
  reachableIds: string[];
  onChoose: (nodeId: string) => void;
  disabled: boolean;
}) {
  const isHorizontal = useIsHorizontal();

  const { byFloor, maxRows, numFloors } = useMemo(() => {
    const byFloor = new Map<number, MapNode[]>();
    for (const node of Object.values(nodes)) {
      const list = byFloor.get(node.floor) ?? [];
      list.push(node);
      byFloor.set(node.floor, list);
    }
    const numFloors = Math.max(...Object.values(nodes).map((n) => n.floor)) + 1;
    let maxRows = 1;
    for (const list of byFloor.values()) maxRows = Math.max(maxRows, list.length);
    return { byFloor, maxRows, numFloors };
  }, [nodes]);

  const width = isHorizontal
    ? HORIZONTAL.PAD * 2 + Math.max(numFloors - 1, 0) * HORIZONTAL.FLOOR_W
    : VERTICAL.PAD * 2 + Math.max(maxRows - 1, 0) * VERTICAL.SIBLING_W;
  const height = isHorizontal
    ? HORIZONTAL.PAD * 2 + Math.max(maxRows - 1, 0) * HORIZONTAL.SIBLING_H
    : VERTICAL.PAD * 2 + Math.max(numFloors - 1, 0) * VERTICAL.FLOOR_H;
  const centerX = width / 2;
  const centerY = height / 2;

  function pos(node: MapNode) {
    const siblingCount = byFloor.get(node.floor)?.length ?? 1;
    const i = nodeIndex(node.id);
    const offset = (i - (siblingCount - 1) / 2) * (isHorizontal ? HORIZONTAL.SIBLING_H : VERTICAL.SIBLING_W);
    if (isHorizontal) {
      return { x: HORIZONTAL.PAD + node.floor * HORIZONTAL.FLOOR_W, y: centerY + offset };
    }
    return { x: centerX + offset, y: height - VERTICAL.PAD - node.floor * VERTICAL.FLOOR_H };
  }

  const reachable = new Set(reachableIds);
  const allNodes = Object.values(nodes);
  const currentFloor = nodes[currentNodeId]?.floor ?? 0;
  // the boss sits at the end of the graph, drawn last so it overlaps nothing
  const drawOrder = [...allNodes].sort((a, b) => Number(a.type === "boss") - Number(b.type === "boss"));

  return (
    <div className={`dungeon-map${disabled ? " is-busy" : ""}`}>
      <svg className="dungeon-map-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Dungeon map">
        {allNodes.flatMap((node) => {
          const from = pos(node);
          return node.connections.map((targetId) => {
            const target = nodes[targetId];
            if (!target) return null;
            const walked = node.visited && target.visited;
            const isNext = node.id === currentNodeId && reachable.has(targetId);
            const classes = ["map-path", walked && "is-walked", isNext && "is-next"].filter(Boolean).join(" ");
            return <path key={`${node.id}->${targetId}`} d={trail(from, pos(target), isHorizontal)} className={classes} />;
          });
        })}

        {drawOrder.map((node) => {
          const { x, y } = pos(node);
          const isCurrent = node.id === currentNodeId;
          const isReachable = reachable.has(node.id);
          const isVisited = node.visited && !isCurrent;
          // rooms on floors already behind you that you never entered
          const isPassed = !node.visited && !isCurrent && node.floor <= currentFloor;
          const style = NODE_STYLE[node.type];
          const r = node.type === "boss" ? BOSS_R : NODE_R;
          const classes = [
            "map-node",
            `type-${node.type}`,
            isCurrent && "is-current",
            isVisited && "is-visited",
            isPassed && "is-passed",
            isReachable && "is-reachable",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <g
              key={node.id}
              className={classes}
              transform={`translate(${x} ${y})`}
              role={isReachable ? "button" : undefined}
              tabIndex={isReachable && !disabled ? 0 : undefined}
              aria-label={`${style.label}, floor ${node.floor}`}
              onMouseEnter={() => {
                if (isReachable && !disabled) sfx.play("hover");
              }}
              onClick={() => {
                if (isReachable && !disabled) onChoose(node.id);
              }}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && isReachable && !disabled) {
                  e.preventDefault();
                  onChoose(node.id);
                }
              }}
            >
              {/* the transform attribute places the node; CSS animates this inner group */}
              <g className="map-node-body" style={{ animationDelay: `${(nodeIndex(node.id) * 0.23 + node.floor * 0.11) % 1.2}s` }}>
                {(isCurrent || isReachable) && <circle className="map-node-halo" r={r + 6} />}
                <circle className="map-node-base" r={r} cy={3} />
                <circle className="map-node-circle" r={r} />
                <circle className="map-node-shine" r={r - 4} />
                <g transform={node.type === "boss" ? "scale(1.25)" : undefined}>
                  {isVisited ? <path className="map-node-check" d="M -6 0 L -1.5 5 L 7 -6" /> : <NodeIcon type={node.type} />}
                </g>
              </g>
              {isCurrent && (
                <g className="map-you" transform={`translate(0 ${-r - 7})`}>
                  <g className="map-you-bob">
                    <path className="map-you-pin" d="M 0 4 L -5.5 -3 A 7.5 7.5 0 1 1 5.5 -3 Z" transform="translate(0 -8)" />
                    <circle className="map-you-dot" cy={-16} r={2.8} />
                  </g>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      <div className="map-legend">
        {(Object.keys(NODE_STYLE) as NodeType[]).map((type) => (
          <span key={type} className={`legend-item type-${type}`}>
            <svg className="legend-icon" viewBox="-12 -12 24 24" width="22" height="22" aria-hidden="true">
              <g className="map-node-body">
                <circle className="map-node-circle" r={10.5} />
                <g transform="scale(0.72)">
                  <NodeIcon type={type} />
                </g>
              </g>
            </svg>
            {NODE_STYLE[type].label}
          </span>
        ))}
      </div>
    </div>
  );
}
