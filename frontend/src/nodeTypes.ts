import type { NodeType } from "./api";

// The map draws each type as a colored coin with an SVG icon (see NodeIcon
// in DungeonMap). Icons are drawn shapes or plain characters, never dingbat
// symbols (swords/skull/crown): those render as fixed-color emoji on most
// platforms and ignore the CSS colors that tell node types apart.
export const NODE_STYLE: Record<NodeType, { symbol: string; label: string }> = {
  combat: { symbol: "C", label: "Fight" },
  elite: { symbol: "E", label: "Elite fight" },
  event: { symbol: "?", label: "Event" },
  shop: { symbol: "$", label: "Shop" },
  rest: { symbol: "R", label: "Rest" },
  boss: { symbol: "B", label: "Boss" },
};
