import { useMemo } from "react";
import type { MapNode } from "../api";
import { NODE_STYLE } from "../nodeTypes";

const COL_W = 74;
const ROW_H = 54;
const PAD = 24;

function nodeIndex(id: string): number {
  return Number(id.split("-")[1]);
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

  const width = PAD * 2 + Math.max(numFloors - 1, 0) * COL_W;
  const height = PAD * 2 + Math.max(maxRows - 1, 0) * ROW_H;
  const centerY = height / 2;

  function pos(node: MapNode) {
    const siblingCount = byFloor.get(node.floor)?.length ?? 1;
    const i = nodeIndex(node.id);
    return {
      x: PAD + node.floor * COL_W,
      y: centerY + (i - (siblingCount - 1) / 2) * ROW_H,
    };
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
              <text className="map-node-symbol">{style.symbol}</text>
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
            <span aria-hidden="true">{NODE_STYLE[type].symbol}</span>
            {NODE_STYLE[type].label}
          </span>
        ))}
      </div>
    </div>
  );
}
