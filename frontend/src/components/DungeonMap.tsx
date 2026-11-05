import { useEffect, useMemo, useState, type CSSProperties } from "react";
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

// A trail between two rooms: one straight line, room to room. Right-angled
// steps all bent at the same spot between two layers, so the trails of a
// layer ran together into one bar and hid which room led to which.
function trail(from: { x: number; y: number }, to: { x: number; y: number }, _horizontal: boolean): string {
  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

// Corner brackets around the room you stand in, with its NOW tag above.
function MapCursor({
  at,
  r,
  floor,
  label,
  enterable,
}: {
  at: { x: number; y: number };
  r: number;
  floor: number;
  label: string;
  enterable: boolean;
}) {
  const d = r + 9;
  const arm = 7;
  const corners = [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ];
  return (
    <g
      className={`map-cursor${enterable ? " is-enterable" : ""}`}
      style={{ transform: `translate(${at.x}px, ${at.y}px)`, "--f": floor } as CSSProperties}
      aria-hidden="true"
    >
      <g className="map-cursor-frame">
        {corners.map(([sx, sy]) => (
          <path key={`${sx}${sy}`} d={`M ${sx * d} ${sy * (d - arm)} V ${sy * d} H ${sx * (d - arm)}`} />
        ))}
      </g>
      {/* the tag bobs by a CSS transform, so the attribute sits on a wrapper */}
      <g transform={`translate(0 ${-r * 1.25 - 16})`}>
        <g className="map-now">
          <rect x={-22} y={-9} width={44} height={17} />
          <text>{label}</text>
        </g>
      </g>
    </g>
  );
}

// What a room ahead holds, for the card shown while it is pointed at.
function roomPreview(
  node: MapNode,
  currentFloor: number,
  act: number,
  numActs: number,
): { title: string; line: string; loot?: string; distance: string } {
  const style = NODE_STYLE[node.type];
  const jumps = node.floor - currentFloor;
  const distance = jumps <= 0 ? "this jump" : jumps === 1 ? "next jump" : `${jumps} jumps away`;
  // deeper layers hold stronger constructs (enemies.escalate)
  const depth = node.floor <= 2 ? "a light one" : node.floor <= 5 ? "a solid one" : "a heavy one";
  switch (node.type) {
    case "combat":
      return { title: style.label, line: `A construct - ${depth} at this depth.`, distance };
    case "elite":
      return { title: style.label, line: "A hardened construct with an affix.", loot: "drops an artifact", distance };
    case "boss":
      return {
        title: style.label,
        line: act < numActs ? "The act's core: phases, barrages, overloads." : "The AGI itself. Three phases.",
        loot: act < numActs ? "drops an artifact" : undefined,
        distance,
      };
    case "shop":
      return { title: style.label, line: "Cards and artifacts for credits, one card removal.", distance };
    case "rest":
      return { title: style.label, line: "Heal, upgrade a card or delete one.", distance };
    default:
      return { title: style.label, line: "Something odd - a choice with a price.", distance };
  }
}

export function DungeonMap({
  nodes,
  currentNodeId,
  reachableIds,
  onChoose,
  onHover,
  onEnter,
  disabled,
  act = 1,
  numActs = 2,
}: {
  nodes: Record<string, MapNode>;
  currentNodeId: string;
  reachableIds: string[];
  onChoose: (nodeId: string) => void;
  onHover?: (nodeId: string | null) => void;
  // set while the current room waits to be entered: clicking it enters
  onEnter?: () => void;
  disabled: boolean;
  act?: number;
  // the act whose boss is the last - its fight ends the run, no artifact
  numActs?: number;
}) {
  const isHorizontal = useIsHorizontal();
  // the room under the pointer, for the route to it
  const [pointed, setPointed] = useState<string | null>(null);

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
  const current = nodes[currentNodeId];
  const currentFloor = current?.floor ?? 0;
  // Where the trails on are drawn from: the room you stand in once it is
  // entered - before that, the room the jump left, while it can be switched.
  const pickPending = current !== undefined && !current.visited;
  const originId = pickPending
    ? allNodes.find((n) => n.visited && n.connections.includes(currentNodeId))?.id
    : currentNodeId;

  // At an act's first layer no room lies behind you: the rooms the pick can
  // still switch between are where the ways start, all of them.
  const starts =
    pickPending && !originId
      ? allNodes.filter((n) => n.floor === currentFloor && (n.id === currentNodeId || reachable.has(n.id))).map((n) => n.id)
      : [];
  const roots = originId ? [originId] : starts;
  const isRoot = (id: string) => roots.includes(id);

  // every room the trails lead to from `from` - at most `hops` jumps on
  const reachedFrom = (from: string[], hops = Infinity) => {
    const seen = new Set<string>();
    let layer = [...from];
    for (let hop = 0; hop < hops && layer.length > 0; hop++) {
      const next: string[] = [];
      for (const id of layer) {
        for (const to of nodes[id]?.connections ?? []) {
          if (!seen.has(to)) {
            seen.add(to);
            next.push(to);
          }
        }
      }
      layer = next;
    }
    return seen;
  };

  // Everything still ahead: the rooms the trails lead to from where you
  // stand (or from the room the pending pick left, or from every start). The
  // rest of the layers to come is out of reach and steps back, so the ways
  // you can still go stand out.
  const ahead = reachedFrom(roots);
  const onWay = (id: string) => isRoot(id) || ahead.has(id);
  // At the start, the next two jumps from the room picked so far stand out
  // from the other starts' ways - where the starts differ - so the pick is
  // made knowing where it leads. Further on the ways mostly meet again.
  const pickedWay = starts.length > 1 ? new Set([currentNodeId, ...reachedFrom([currentNodeId], 2)]) : null;
  // A room pointed at: every way there from here lights up - a start pointed
  // at, every way on from it.
  const route = new Set<string>();
  if (pointed && starts.includes(pointed)) {
    route.add(pointed);
    for (const id of reachedFrom([pointed])) route.add(id);
  } else if (pointed && ahead.has(pointed)) {
    const leadsThere = (id: string, seen: Map<string, boolean>): boolean => {
      if (id === pointed) return true;
      if (seen.has(id)) return seen.get(id) as boolean;
      seen.set(id, false);
      const there = (nodes[id]?.connections ?? []).some((next) => ahead.has(next) && leadsThere(next, seen));
      seen.set(id, there);
      return there;
    };
    const seen = new Map<string, boolean>();
    for (const id of [...roots, ...ahead]) if (leadsThere(id, seen)) route.add(id);
  }

  // the jump just made: a packet runs the trail from the room it left
  const [jump, setJump] = useState<{ from: string; to: string; id: number } | null>(null);
  const [lastCurrent, setLastCurrent] = useState(currentNodeId);
  if (currentNodeId !== lastCurrent) {
    setLastCurrent(currentNodeId);
    if (nodes[lastCurrent]?.connections.includes(currentNodeId) || pickPending) {
      const from = nodes[lastCurrent]?.connections.includes(currentNodeId) ? lastCurrent : originId;
      if (from) setJump({ from, to: currentNodeId, id: (jump?.id ?? 0) + 1 });
    }
  }

  const preview = pointed && nodes[pointed] ? roomPreview(nodes[pointed], currentFloor, act, numActs) : null;
  const previewAt = pointed && nodes[pointed] ? pos(nodes[pointed]) : null;

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
            const isNext = node.id === originId && reachable.has(targetId);
            const isAhead = onWay(node.id) && ahead.has(targetId);
            const onRoute = route.has(node.id) && route.has(targetId);
            const onPicked = pickedWay !== null && pickedWay.has(node.id) && pickedWay.has(targetId);
            const classes = [
              "map-path",
              walked && "is-walked",
              isNext && "is-next",
              isAhead && "is-ahead",
              onPicked && "is-picked-way",
              onRoute && "is-route",
              !walked && !isAhead && "is-cut",
            ]
              .filter(Boolean)
              .join(" ");
            return <path key={`${node.id}->${targetId}`} d={trail(from, pos(target), isHorizontal)} className={classes} />;
          });
        })}
        {jump && nodes[jump.from] && nodes[jump.to] && (
          <g key={jump.id} className="map-packet" aria-hidden="true">
            <path id={`packet-${jump.id}`} d={trail(pos(nodes[jump.from]), pos(nodes[jump.to]), isHorizontal)} fill="none" />
            <circle r="6">
              <animateMotion dur="0.55s" fill="freeze" calcMode="spline" keySplines="0.4 0 0.2 1" keyTimes="0;1">
                <mpath href={`#packet-${jump.id}`} />
              </animateMotion>
              <animate attributeName="opacity" values="1;1;0" keyTimes="0;0.8;1" dur="0.8s" fill="freeze" />
            </circle>
            <circle r="12" className="map-packet-glow">
              <animateMotion dur="0.55s" fill="freeze" calcMode="spline" keySplines="0.4 0 0.2 1" keyTimes="0;1">
                <mpath href={`#packet-${jump.id}`} />
              </animateMotion>
              <animate attributeName="opacity" values="0.6;0.6;0" keyTimes="0;0.8;1" dur="0.8s" fill="freeze" />
            </circle>
          </g>
        )}
        {/* the picked trail on top of the ones it shares a stretch with */}
        {pickPending && originId && current && (
          <path className="map-path is-picked" d={trail(pos(nodes[originId]), pos(current), isHorizontal)} />
        )}

        {allNodes.map((node) => {
          const { x, y } = pos(node);
          const isCurrent = node.id === currentNodeId;
          const isReachable = reachable.has(node.id);
          const isEnterable = isCurrent && onEnter !== undefined;
          const isVisited = node.visited && !isCurrent;
          // rooms in eras already behind you that you never entered (the
          // ones the pick can still switch to are not behind you yet)
          const isPassed = !node.visited && !isCurrent && !isReachable && node.floor <= currentFloor;
          const style = NODE_STYLE[node.type];
          const r = node.type === "boss" ? BOSS_R : NODE_R;
          const classes = [
            "map-node",
            `type-${node.type}`,
            isCurrent && "is-current",
            isVisited && "is-visited",
            isPassed && "is-passed",
            isReachable && "is-reachable",
            isEnterable && "is-enterable",
            // a later room no trail from here leads to
            !isCurrent && !node.visited && node.floor > currentFloor && !ahead.has(node.id) && "is-cut",
            route.has(node.id) && node.id !== originId && "is-on-route",
            pickedWay?.has(node.id) && node.id !== currentNodeId && "is-on-picked-way",
          ]
            .filter(Boolean)
            .join(" ");
          const interactive = (isReachable || isEnterable) && !disabled;
          const activate = () => {
            if (!interactive) return;
            if (isEnterable) onEnter?.();
            else onChoose(node.id);
          };
          return (
            <g
              key={node.id}
              className={classes}
              transform={`translate(${x} ${y})`}
              // stagger for the CSS: layers fade in one after another, and
              // reachable rooms don't bob in lockstep
              style={{ "--f": node.floor, "--i": nodeIndex(node.id) } as CSSProperties}
              role={isReachable || isEnterable ? "button" : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-label={`${isEnterable ? "Enter " : ""}${style.label}, ${layerLabel(node.floor, numFloors, act)}`}
              onMouseEnter={() => {
                if (ahead.has(node.id) || starts.includes(node.id)) setPointed(node.id);
                if (!interactive) return;
                sfx.play("hover");
                if (isReachable) onHover?.(node.id);
              }}
              onMouseLeave={() => {
                setPointed((p) => (p === node.id ? null : p));
                if (interactive && isReachable) onHover?.(null);
              }}
              onFocus={() => {
                if (interactive && isReachable) onHover?.(node.id);
              }}
              onClick={activate}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && interactive) {
                  e.preventDefault();
                  activate();
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
                {/* the harder fights pay an artifact: a gem on their corner */}
                {!node.visited && (node.type === "elite" || (node.type === "boss" && act < numActs)) && (
                  <g className="map-node-loot" transform={`translate(${r - 1} ${-r + 1})`}>
                    <title>Drops an artifact</title>
                    <path d="M0 -5.5 L4.5 0 L0 5.5 L-4.5 0 Z" />
                  </g>
                )}
              </g>
            </g>
          );
        })}

        {/* One marker for where you stand, drawn over the rooms and placed by a
            CSS transform, so it glides over when the pick is switched (or a
            jump made) instead of popping up on the other room. */}
        {current && (
          <MapCursor
            at={pos(current)}
            r={current.type === "boss" ? BOSS_R : NODE_R}
            floor={current.floor}
            label={pickPending && reachable.size > 0 ? "NEXT" : "NOW"}
            enterable={onEnter !== undefined}
          />
        )}
      </svg>
      {preview && previewAt && (
        <div
          className={`map-preview type-${nodes[pointed as string].type}`}
          style={{ left: `${(previewAt.x / width) * 100}%`, top: `${(previewAt.y / height) * 100}%` }}
          aria-hidden="true"
        >
          <b>{preview.title}</b>
          <span>{preview.line}</span>
          {preview.loot && <em>◆ {preview.loot}</em>}
          <small>{preview.distance}</small>
        </div>
      )}

      <div className="map-legend">
        {(Object.keys(NODE_STYLE) as NodeType[]).map((type) => (
          <span key={type} className="legend-item">
            <NodeBadge type={type} />
            {NODE_STYLE[type].label}
          </span>
        ))}
        <span className="legend-item">
          <svg className="legend-loot" viewBox="-6 -6 12 12" width={12} height={12} aria-hidden="true">
            <path d="M0 -5.5 L4.5 0 L0 5.5 L-4.5 0 Z" />
          </svg>
          Artifact
        </span>
      </div>
    </div>
  );
}
