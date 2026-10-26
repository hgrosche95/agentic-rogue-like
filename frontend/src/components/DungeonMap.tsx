import { useEffect, useMemo, useState } from "react";
import type { MapNode, NodeType } from "../api";
import { sfx } from "../audio";
import { layerLabel } from "../layers";
import { NODE_STYLE } from "../nodeTypes";

// The call stack on narrow screens: layers climb bottom-to-top, siblings spread
// left-right - a vertical ascent the player scrolls through. On wide
// (desktop) screens the same graph lies down sideways instead - layers run
// left-to-right - so it fits the viewport without scrolling.
const VERTICAL = { SIBLING_W: 70, FLOOR_H: 84, PAD_X: 34, PAD_TOP: 44, PAD_BOTTOM: 30, LABEL: 38 };
const HORIZONTAL = { FLOOR_W: 112, SIBLING_H: 76, PAD_X: 40, PAD_TOP: 88, PAD_BOTTOM: 34 };
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

// A square pixel tile around the origin, `r` being the radius of the matching circle.
function Tile({ r, className }: { r: number; className: string }) {
  const d = Math.round(r * 0.9);
  return <rect className={className} x={-d} y={-d} width={2 * d} height={2 * d} />;
}

// The icon on a node, drawn in a 16x16 box around the origin. Shapes rather
// than dingbat/emoji glyphs, so the color stays controllable per node state -
// see the comment in nodeTypes.ts.
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
          <circle className="node-icon-hole" cx="-2.4" cy="0.6" r="1.7" />
          <circle className="node-icon-hole" cx="2.4" cy="0.6" r="1.7" />
        </g>
      );
    case "rest":
      return (
        <g className="node-icon">
          <path d="M0 -7.5 C4.5 -3 5.5 0.5 3.4 3.4 C2 5.2 -2 5.2 -3.4 3.4 C-5.4 0.6 -3.2 -2 -1.6 -3.2 C-1.2 -1.6 -0.4 -0.8 0.6 -0.6 C-0.2 -3 0 -5.2 0 -7.5 Z" />
        </g>
      );
    case "boss":
      return (
        <g className="node-icon">
          <path d="M-8 4.5 L-8.5 -4.5 L-4 -0.5 L0 -7 L4 -0.5 L8.5 -4.5 L8 4.5 Z" />
        </g>
      );
    default:
      return <text className="node-icon-text">{NODE_STYLE[type].symbol}</text>;
  }
}

// The small tile badge used by the legend and the next-jump panel.
export function NodeBadge({ type, size = 22 }: { type: NodeType; size?: number }) {
  return (
    <svg className={`node-badge type-${type}`} viewBox="-14 -14 28 28" width={size} height={size} aria-hidden="true">
      <Tile r={10} className="map-node-shape" />
      <g transform="scale(0.7)">
        <NodeIcon type={type} />
      </g>
    </svg>
  );
}

// A trail between two rooms: a right-angled step along the direction the layers
// run, like a path on a pixel board.
function trail(from: { x: number; y: number }, to: { x: number; y: number }, horizontal: boolean): string {
  if (horizontal) {
    const mx = Math.round((from.x + to.x) / 2);
    return `M ${from.x} ${from.y} H ${mx} V ${to.y} H ${to.x}`;
  }
  const my = Math.round((from.y + to.y) / 2);
  return `M ${from.x} ${from.y} V ${my} H ${to.x} V ${to.y}`;
}

export function DungeonMap({
  nodes,
  currentNodeId,
  reachableIds,
  onChoose,
  onHover,
  disabled,
  act = 1,
}: {
  nodes: Record<string, MapNode>;
  currentNodeId: string;
  reachableIds: string[];
  onChoose: (nodeId: string) => void;
  onHover?: (nodeId: string | null) => void;
  disabled: boolean;
  act?: number;
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
    ? HORIZONTAL.PAD_X * 2 + Math.max(numFloors - 1, 0) * HORIZONTAL.FLOOR_W
    : VERTICAL.LABEL + VERTICAL.PAD_X * 2 + Math.max(maxRows - 1, 0) * VERTICAL.SIBLING_W;
  const height = isHorizontal
    ? HORIZONTAL.PAD_TOP + HORIZONTAL.PAD_BOTTOM + Math.max(maxRows - 1, 0) * HORIZONTAL.SIBLING_H
    : VERTICAL.PAD_TOP + VERTICAL.PAD_BOTTOM + Math.max(numFloors - 1, 0) * VERTICAL.FLOOR_H;

  function floorPos(floor: number) {
    return isHorizontal
      ? HORIZONTAL.PAD_X + floor * HORIZONTAL.FLOOR_W
      : height - VERTICAL.PAD_BOTTOM - floor * VERTICAL.FLOOR_H;
  }

  function pos(node: MapNode) {
    const siblingCount = byFloor.get(node.floor)?.length ?? 1;
    const offset = (nodeIndex(node.id) - (siblingCount - 1) / 2) * (isHorizontal ? HORIZONTAL.SIBLING_H : VERTICAL.SIBLING_W);
    if (isHorizontal) {
      const centerY = HORIZONTAL.PAD_TOP + (height - HORIZONTAL.PAD_TOP - HORIZONTAL.PAD_BOTTOM) / 2;
      return { x: floorPos(node.floor), y: centerY + offset };
    }
    const centerX = VERTICAL.LABEL + (width - VERTICAL.LABEL) / 2;
    return { x: centerX + offset, y: floorPos(node.floor) };
  }

  const reachable = new Set(reachableIds);
  const allNodes = Object.values(nodes);
  const currentFloor = nodes[currentNodeId]?.floor ?? 0;

  return (
    <div className={`dungeon-map${disabled ? " is-busy" : ""}`}>
      <svg className="dungeon-map-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Call stack map">
        {Array.from({ length: numFloors }, (_, floor) => {
          const at = floorPos(floor);
          const classes = ["map-era", floor === currentFloor && "is-now", floor < currentFloor && "is-past"]
            .filter(Boolean)
            .join(" ");
          return isHorizontal ? (
            <g key={floor} className={classes}>
              <line className="map-era-line" x1={at} y1={44} x2={at} y2={height - 8} />
              <text className="map-era-label" x={at} y={28}>
                {layerLabel(floor, numFloors, act)}
              </text>
            </g>
          ) : (
            <g key={floor} className={classes}>
              <line className="map-era-line" x1={VERTICAL.LABEL + 4} y1={at} x2={width - 6} y2={at} />
              <text className="map-era-label is-side" x={4} y={at}>
                {layerLabel(floor, numFloors, act)}
              </text>
            </g>
          );
        })}

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

        {allNodes.map((node) => {
          const { x, y } = pos(node);
          const isCurrent = node.id === currentNodeId;
          const isReachable = reachable.has(node.id);
          const isVisited = node.visited && !isCurrent;
          // rooms in eras already behind you that you never entered
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
          const interactive = isReachable && !disabled;
          return (
            <g
              key={node.id}
              className={classes}
              transform={`translate(${x} ${y})`}
              role={isReachable ? "button" : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-label={`${style.label}, ${layerLabel(node.floor, numFloors, act)}`}
              onMouseEnter={() => {
                if (!interactive) return;
                sfx.play("hover");
                onHover?.(node.id);
              }}
              onMouseLeave={() => {
                if (interactive) onHover?.(null);
              }}
              onFocus={() => {
                if (interactive) onHover?.(node.id);
              }}
              onClick={() => {
                if (interactive) onChoose(node.id);
              }}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && interactive) {
                  e.preventDefault();
                  onChoose(node.id);
                }
              }}
            >
              {/* the transform attribute places the node; CSS animates this inner group */}
<g className="map-node-body">
                {(isCurrent || isReachable) && <rect className="map-node-halo" x={-r - 6} y={-r - 6} width={2 * r + 12} height={2 * r + 12} />}
                <Tile r={r} className="map-node-shape" />
                <Tile r={r - 5} className="map-node-inner" />
                <g transform={node.type === "boss" ? "scale(1.3)" : undefined}>
                  {isVisited ? <path className="map-node-check" d="M -6 0 L -1.5 5 L 7 -6" /> : <NodeIcon type={node.type} />}
                </g>
              </g>
              {isCurrent && (
                <g className="map-now" transform={`translate(0 ${-r * 1.25 - 16})`}>
                  <rect x={-22} y={-9} width={44} height={17} />
                  <text>NOW</text>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      <div className="map-legend">
        {(Object.keys(NODE_STYLE) as NodeType[]).map((type) => (
          <span key={type} className="legend-item">
            <NodeBadge type={type} />
            {NODE_STYLE[type].label}
          </span>
        ))}
      </div>
    </div>
  );
}
