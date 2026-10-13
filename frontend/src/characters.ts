import { createContext } from "react";
import type { Character, CharacterView } from "./api";

// Shown until GET /characters answers, and if it never does - mirrors
// characters.py, so the title screen works against an older API too.
export const FALLBACK_CHARACTERS: CharacterView[] = [
  {
    id: "chronos",
    name: "Dr. Chronos",
    title: "Human · Time traveller",
    description: "Plays steady: draws 3 cards at the end of every turn.",
    hp: 45,
    token_limit: null,
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
