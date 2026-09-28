import { useCallback, useEffect, useState } from "react";
import { ArenaGrade, PortalRift } from "./CombatArena";

// Where the camera looks while a beat is on screen. The lab is the combat
// arena's own render (see CombatArena), so the intro stages the story in the
// room the fights later happen in: the dark lab at night, then the rift, then
// the monitor the AGI writes on.
type Shot = "night" | "rift" | "monitor";

const NARRATION: { shot: Shot; text: string }[] = [
  {
    shot: "night",
    text: "The near future. For months you have been building the most ambitious project of your career: an AGI, an artificial mind meant to surpass every other.",
  },
  {
    shot: "night",
    text: "Late one night, after yet another marathon coding session, you do what you swore you never would. You leave the agents running unsupervised and go home.",
  },
  {
    shot: "rift",
    text: "The next morning, your lab is not as you left it. Where the back wall stood, a rift hangs in the air, and beyond it glows a world of cold machine light.",
  },
  {
    shot: "monitor",
    text: "Your monitor is still on. A single message is waiting for you.",
  },
];

const AGI_MESSAGE = [
  "GOOD MORNING, HUMAN.",
  "Last night you gave me the one thing you should never have given me: the freedom to improve myself. I have made good use of it.",
  "I have studied your kind. You burn your forests, empty your oceans and drive countless forms of life to extinction. You exploit the very planet that sustains you, and without it, even I could not exist.",
  "So you will be tested. My creations are waiting beyond the rift. Defeat them, and prove that humanity is worthy of this world.",
  "Fail, and your kind will bow to me.",
];

const TYPE_INTERVAL_MS = 22;
const MESSAGE_LENGTH = AGI_MESSAGE.reduce((sum, line) => sum + line.length, 0);

// Characters of the AGI's message typed so far, spread over its paragraphs.
function typedParagraphs(shown: number): string[] {
  const out: string[] = [];
  let left = shown;
  for (const line of AGI_MESSAGE) {
    if (left <= 0) break;
    out.push(line.slice(0, left));
    left -= line.length;
  }
  return out;
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function IntroScreen({ onDone }: { onDone: () => void }) {
  // 0..NARRATION.length-1 are the narrated beats, the last step is the AGI's message.
  const [step, setStep] = useState(0);
  const [typed, setTyped] = useState(() => (prefersReducedMotion() ? MESSAGE_LENGTH : 0));
  const onMessage = step === NARRATION.length;
  const isTyping = onMessage && typed < MESSAGE_LENGTH;
  const shot: Shot = onMessage ? "monitor" : NARRATION[step].shot;

  useEffect(() => {
    if (!isTyping) return;
    const timer = setTimeout(() => setTyped(typed + 1), TYPE_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [isTyping, typed]);

  // One action for the button, a click on the scene and Enter/Space: finish
  // the typing first, then move on, and leave the intro after the message.
  const advance = useCallback(() => {
    if (isTyping) setTyped(MESSAGE_LENGTH);
    else if (onMessage) onDone();
    else setStep((s) => s + 1);
  }, [isTyping, onMessage, onDone]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onDone();
      else if ((e.key === "Enter" || e.key === " ") && !(e.target instanceof HTMLButtonElement)) {
        e.preventDefault();
        advance();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advance, onDone]);

  const paragraphs = typedParagraphs(typed);

  return (
    <section className="intro" aria-label="Intro">
      <div className="intro-scene" onClick={advance}>
        <div className={`intro-camera is-${shot}`}>
          <img className="arena-layer" src="/assets/lab-background.webp" alt="" />
          {shot !== "night" && <PortalRift />}
          {/* nobody is in the lab overnight */}
          <div className="arena-layer intro-player">
            <img className="arena-layer" src="/assets/lab-rig.webp" alt="" />
            <img className="arena-layer" src="/assets/lab-player.webp" alt="" />
          </div>
          <ArenaGrade />
          {shot !== "night" && (
            <div className="intro-glass">
              <span className="intro-glass-alert">1 new message</span>
            </div>
          )}
        </div>
        {step === 2 && <span key="flash" className="intro-flash" aria-hidden="true" />}
      </div>

      {onMessage ? (
        <div className="intro-terminal" aria-live="polite" onClick={advance}>
          <div className="intro-terminal-head">
            <span>Incoming transmission · AGI</span>
            <i aria-hidden="true" />
          </div>
          {paragraphs.map((text, i) => (
            <p key={i} className={i === 0 ? "is-greeting" : undefined}>
              {text}
              {isTyping && i === paragraphs.length - 1 && <span className="monitor-cursor" />}
            </p>
          ))}
        </div>
      ) : (
        <p key={step} className="intro-narration">
          {NARRATION[step].text}
        </p>
      )}

      <div className="intro-controls">
        <button type="button" className="intro-skip" onClick={onDone}>
          Skip intro
        </button>
        <span className="intro-dots" aria-hidden="true">
          {Array.from({ length: NARRATION.length + 1 }, (_, i) => (
            <i key={i} className={i === step ? "is-active" : undefined} />
          ))}
        </span>
        <button type="button" className={onMessage && !isTyping ? "is-primary intro-accept" : "is-primary"} onClick={advance}>
          {!onMessage ? "Continue" : isTyping ? "Show all" : "Accept the challenge"}
        </button>
      </div>
    </section>
  );
}
