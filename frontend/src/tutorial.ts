// Whether the first fight's coach marks (components/Tutorial) have been shown
// in each mode. Storage can be blocked (private mode): they then simply show
// again next time.

export type TutorialMode = "program" | "classic";

const SEEN_KEY = "agentic-rogue-like:tutorial-seen:";

export function hasSeenTutorial(mode: TutorialMode): boolean {
  try {
    return localStorage.getItem(SEEN_KEY + mode) === "1";
  } catch {
    return false;
  }
}

export function rememberTutorialSeen(mode: TutorialMode) {
  try {
    localStorage.setItem(SEEN_KEY + mode, "1");
  } catch {
    // Nothing to do - see hasSeenTutorial.
  }
}
