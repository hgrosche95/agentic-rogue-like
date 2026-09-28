import type { NodeType } from "./api";

// The map draws each type as a colored diamond with an SVG icon (see NodeIcon
// in DungeonMap). Icons are drawn shapes or plain characters, never dingbat
// symbols (swords/skull/crown): those render as fixed-color emoji on most
// platforms and ignore the CSS colors that tell node types apart.
export const NODE_STYLE: Record<NodeType, { symbol: string; label: string; blurb: string }> = {
  combat: { symbol: "C", label: "Fight", blurb: "A construct of the AGI blocks the timeline." },
  elite: { symbol: "E", label: "Elite", blurb: "A hardened construct. Tougher fight, better loot." },
  event: { symbol: "?", label: "Anomaly", blurb: "Something odd in this era. Choose how to react." },
  shop: { symbol: "$", label: "Black market", blurb: "Trade credits for an edge." },
  rest: { symbol: "R", label: "Safehouse", blurb: "Catch your breath and patch yourself up." },
  boss: { symbol: "B", label: "Core AI", blurb: "The AGI itself, waiting at the end of time." },
};
