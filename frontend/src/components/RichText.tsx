import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

// Game terms in card, artifact and deal texts, each with a short explanation
// that shows on hover. The UI calls the piles Source / Cache / Purged, the
// card texts say draw pile / graveyard / banished - the tips tie them together.
const KEYWORDS: { pattern: RegExp; tip: string }[] = [
  {
    pattern: /\bgraveyard\b/i,
    tip: "Graveyard (the Cache pile): played and discarded cards land here. When Source runs dry, it is shuffled back in.",
  },
  {
    pattern: /\bbanish(?:ed)?\b/i,
    tip: "Banished (the Purged pile): gone for the rest of the fight. One-shot cards end up here; they are back next fight.",
  },
  {
    pattern: /\bone-shot\b/i,
    tip: "One-shot: banished after it is played - gone for the rest of the fight, back in the next one.",
  },
  {
    pattern: /\bmalware\b/i,
    tip: "Malware: the infected side loses that much HP at the end of each turn, then one stack fades. Ignores block.",
  },
  {
    pattern: /\bexpose[ds]?\b/i,
    tip: "Exposed: attack cards deal 50% more to it, for that many turns.",
  },
  {
    pattern: /\bthrottle[ds]?\b/i,
    tip: "Throttled: it deals 25% less, for that many of its turns.",
  },
  {
    pattern: /\bpermanent\b/i,
    tip: "Permanent: stays in play and keeps working every turn. Classic: takes a slot on the field. Program: runs in the background, no limit.",
  },
  {
    pattern: /\bcontrol flow\b/i,
    tip: "Control flow (program mode): queued like an action and steers the actions around it when the program runs - order matters.",
  },
  {
    pattern: /\btokens?\b/i,
    tip: "Tokens (Vibe-Coder): cards cost tokens from the context window. Past it, a card may hallucinate and backfire.",
  },
  {
    pattern: /\bhallucinat\w*/i,
    tip: "Hallucination: a card played past the context window may misfire - an attack hits you, a block or heal goes to the enemy.",
  },
  {
    pattern: /\bglitch\b/i,
    tip: "Glitch: a dead card. Play it to flush it out for this fight.",
  },
  {
    pattern: /\(\+ATK\)/,
    tip: "+ATK: your attack stat is added to the damage.",
  },
];

const ANY_KEYWORD = new RegExp(KEYWORDS.map((k) => k.pattern.source).join("|"), "gi");

function tipFor(word: string): string | undefined {
  return KEYWORDS.find((k) => new RegExp(`^(?:${k.pattern.source})$`, "i").test(word))?.tip;
}

// `text` with every game term marked for the tooltip layer (see Tooltips).
export function RichText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(ANY_KEYWORD)) {
    const tip = tipFor(match[0]);
    if (!tip) continue;
    parts.push(text.slice(last, match.index));
    parts.push(
      <span key={match.index} className="keyword" data-tip={tip}>
        {match[0]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

// One tooltip for the whole page: whatever [data-tip] the pointer is over.
// It lives in a portal with a fixed position, so it isn't clipped by the
// card or overlay it belongs to.
export function Tooltips() {
  const [tip, setTip] = useState<{ text: string; x: number; y: number; below: boolean } | null>(null);
  useEffect(() => {
    function over(event: PointerEvent) {
      const el = (event.target as Element | null)?.closest?.("[data-tip]");
      if (!el) {
        setTip(null);
        return;
      }
      const box = el.getBoundingClientRect();
      // near the top of the screen it opens downwards instead
      const below = box.top < 120;
      setTip({
        text: el.getAttribute("data-tip") ?? "",
        x: box.left + box.width / 2,
        y: below ? box.bottom : box.top,
        below,
      });
    }
    const hide = () => setTip(null);
    document.addEventListener("pointerover", over);
    window.addEventListener("scroll", hide, true);
    return () => {
      document.removeEventListener("pointerover", over);
      window.removeEventListener("scroll", hide, true);
    };
  }, []);
  if (!tip) return null;
  return createPortal(
    <div className={`tooltip${tip.below ? " is-below" : ""}`} role="tooltip" style={{ left: tip.x, top: tip.y }}>
      {tip.text}
    </div>,
    document.body,
  );
}
