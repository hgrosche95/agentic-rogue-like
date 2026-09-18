import { useEffect, useMemo, useState } from "react";
import type { MapNode } from "../api";
import { NODE_STYLE } from "../nodeTypes";

// Bergpfad on narrow screens: floors climb bottom-to-top, siblings spread
// left-right - a vertical ascent the player scrolls through. On wide
// (desktop) screens the same graph lies down sideways instead - floors run
// left-to-right - so it fits the viewport without scrolling.
const VERTICAL = { SIBLING_W: 62, FLOOR_H: 72, PAD: 26 };
const HORIZONTAL = { FLOOR_W: 88, SIBLING_H: 54, PAD: 28 };
const HORIZONTAL_QUERY = "(min-width: 900px)";

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

// Crossed swords, drawn as plain strokes (not a dingbat/emoji glyph) so the
// color stays controllable per node state - see the comment in nodeTypes.ts.
function SwordGlyph({ className = "" }: { className?: string }) {
  return (
    <>
      <line className={`map-node-icon ${className}`} x1="-7" y1="7" x2="6" y2="-6" />
      <line className={`map-node-icon ${className}`} x1="7" y1="7" x2="-6" y2="-6" />
      <line className={`map-node-icon ${className}`} x1="3" y1="-3.5" x2="6.5" y2="-1" />
      <line className={`map-node-icon ${className}`} x1="-3" y1="-3.5" x2="-6.5" y2="-1" />
      <circle className={`map-node-icon-pommel ${className}`} cx="-7" cy="7" r="1.4" />
      <circle className={`map-node-icon-pommel ${className}`} cx="7" cy="7" r="1.4" />
    </>
  );
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

  return (
    <div className="dungeon-map">
      <svg className="dungeon-map-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Dungeon map">
        {allNodes.flatMap((node) => {
          const from = pos(node);
          return node.connections.map((targetId) => {
            const target = nodes[targetId];
            if (!target) return null;
            const to = pos(target);
            const walked = node.visited && target.visited;
            return (
              <line
                key={`${node.id}->${targetId}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                className={walked ? "map-path is-walked" : "map-path"}
              />
            );
          });
        })}

        {allNodes.map((node) => {
          const { x, y } = pos(node);
          const isCurrent = node.id === currentNodeId;
          const isReachable = reachable.has(node.id);
          const style = NODE_STYLE[node.type];
          const classes = [
            "map-node",
            `type-${node.type}`,
            isCurrent && "is-current",
            node.visited && !isCurrent && "is-visited",
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
              {isCurrent && <circle className="map-node-ring" r={17} />}
              <circle className="map-node-circle" r={13} />
              {node.visited && !isCurrent ? (
                <path className="map-node-check" d="M -6 0 L -1.5 5 L 7 -6" />
              ) : node.type === "combat" ? (
                <SwordGlyph />
              ) : (
                <text className="map-node-symbol">{style.symbol}</text>
              )}
              {isCurrent && (
                <line
                  className="map-node-needle"
                  x1={0}
                  y1={0}
                  x2={isHorizontal ? 10 : 0}
                  y2={isHorizontal ? 0 : -10}
                />
              )}
              {isCurrent && (
                <text className="you-are-here" y={24}>
                  you
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="map-legend">
        {(Object.keys(NODE_STYLE) as (keyof typeof NODE_STYLE)[]).map((type) => (
          <span key={type} className={`legend-item type-${type}`}>
            {type === "combat" ? (
              <svg className="legend-icon" viewBox="-8 -8 16 16" width="14" height="14" aria-hidden="true">
                <SwordGlyph />
              </svg>
            ) : (
              <span aria-hidden="true">{NODE_STYLE[type].symbol}</span>
            )}
            {NODE_STYLE[type].label}
          </span>
        ))}
      </div>
    </div>
  );
}
