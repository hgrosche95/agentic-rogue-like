import type { NodeType } from "./api";

// Plain letters, not dingbat symbols (swords/skull/crown): those render as
// fixed-color emoji on most platforms and ignore the `color` CSS below,
// which broke the whole point of color-coding node types by hand.
export const NODE_STYLE: Record<NodeType, { symbol: string; label: string; color: string }> = {
  combat: { symbol: "C", label: "Fight", color: "var(--tangerine)" },
  elite: { symbol: "E", label: "Elite fight", color: "var(--maroon)" },
  event: { symbol: "?", label: "Event", color: "var(--violet)" },
  shop: { symbol: "$", label: "Shop", color: "var(--gold)" },
  rest: { symbol: "R", label: "Rest", color: "var(--green)" },
  boss: { symbol: "B", label: "Boss", color: "var(--maroon)" },
};
