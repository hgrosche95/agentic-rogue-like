import { useMemo } from "react";
import type { MapNode } from "../api";
import { NODE_STYLE } from "../nodeTypes";

const COL_W = 76;
const ROW_H = 60;
const PAD = 28;

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

  const width = PAD * 2 + (numFloors - 1) * COL_W;
  const height = PAD * 2 + maxRows * ROW_H;
  const centerY = PAD + (maxRows * ROW_H) / 2;

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
      <div className="dungeon-map-inner" style={{ width, height }}>
        <svg className="dungeon-map-lines" width={width} height={height}>
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
        </svg>

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
            <button
              key={node.id}
              className={classes}
              style={{ left: x, top: y }}
              disabled={disabled || !isReachable}
              onClick={() => onChoose(node.id)}
              title={`${style.label} · floor ${node.floor}`}
            >
              <span aria-hidden="true">{style.symbol}</span>
              {isCurrent && <span className="you-are-here">you</span>}
            </button>
          );
        })}
      </div>

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
