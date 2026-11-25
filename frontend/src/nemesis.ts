// Last run's killer, kept in this browser until the next run takes it along
// (api.createRun) - it returns there as the first elite of act 1. Storage
// can be blocked (private mode) or hold garbage: every access is guarded,
// and anything that isn't a nemesis reads as none. The server checks it
// again and drops what it can't fight with.

import type { NemesisSpec } from "./api";

const KEY = "agentic-rogue-like:nemesis";

function isNemesis(value: unknown): value is NemesisSpec {
  if (typeof value !== "object" || value === null) return false;
  const n = value as Record<string, unknown>;
  return typeof n.name === "string" && typeof n.attack_name === "string" && Array.isArray(n.moves);
}

export function loadNemesis(): NemesisSpec | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    return isNemesis(value) ? value : null;
  } catch {
    return null;
  }
}

export function saveNemesis(nemesis: NemesisSpec) {
  try {
    localStorage.setItem(KEY, JSON.stringify(nemesis));
  } catch {
    // blocked or full - this killer just won't come back
  }
}

export function clearNemesis() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // nothing to do - see saveNemesis
  }
}
