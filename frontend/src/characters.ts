import { createContext } from "react";
import type { Character, CharacterView } from "./api";

// Shown until GET /characters answers, and if it never does (the API may
// still be waking up) - mirrors characters.py, so both stay pickable.
export const FALLBACK_CHARACTERS: CharacterView[] = [
  {
    id: "chronos",
    name: "Dr. Chronos",
    title: "Human · Hacker",
    description: "Plays steady: draws 3 cards at the end of every turn.",
    hp: 45,
    token_limit: null,
  },
  {
    id: "vibe_coder",
    name: "Vibe-Coder",
    title: "Human · Prompts, doesn't type",
    description:
      "Draws a card for every card he plays, but only 2 at the end of the turn. Every card costs tokens from a 4-token context window, 3 of which free up every turn - past it, cards may hallucinate and backfire.",
    hp: 45,
    token_limit: 4,
  },
];

// What the combat HUD calls the player, per character.
export const HERO: Record<Character, { name: string; initials: string }> = {
  chronos: { name: "Dr. Chronos", initials: "DC" },
  vibe_coder: { name: "Vibe-Coder", initials: "VC" },
};

// Whether cards show their token cost - only for a character with a context
// window, everyone else never pays it.
export const ShowTokensContext = createContext(false);
