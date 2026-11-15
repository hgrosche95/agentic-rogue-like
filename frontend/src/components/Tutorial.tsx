import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { sfx } from "../audio";
import { rememberTutorialSeen, type TutorialMode } from "../tutorial";
import { RichText } from "./RichText";

// The first fight of each mode walks the player through it: a few coach
// marks, each a glowing ring around a real part of the table and a note
// beside it. Nothing is blocked - the ring and the note let the pointer (and
// a dragged card) through, all but the note's own buttons - and a step that
// asks for an action moves on once it is done. Shown once per mode, again
// from the help sheet.

interface Step {
  // what the ring goes around (the first match)
  target: string;
  // a bigger box the note keeps clear of, when the target's surroundings
  // matter too (the zone's head with its help button)
  clear?: string;
  title: string;
  text: string;
  // the step moves on by itself once a card is played / the turn is ended
  // (it can still be moved on with Next)
  advanceOn?: "play" | "end";
}

const INTENT = ".vs-hud.is-enemy .intent-badge";

const STEPS: Record<TutorialMode, Step[]> = {
  program: [
    {
      target: ".program-lines",
      clear: ".field-zone",
      title: "Queue your attacks",
      text: "Drag an attack from your hand into a line - or click it, then the line. Nothing happens yet: the lines run left to right when the program runs.",
      advanceOn: "play",
    },
    {
      target: ".program-background",
      clear: ".field-zone",
      title: "The background",
      text: "Permanents don't take a line: they go to the background and boost the whole program, every turn.",
    },
    {
      target: INTENT,
      title: "Enemy intent",
      text: "Watch the enemy's next move. An Interrupt cuts your program after a few lines - put what matters first.",
    },
    {
      target: ".end-turn-button",
      title: "Run it",
      text: "Press Run program: your lines run one by one, then the enemy acts.",
      advanceOn: "end",
    },
  ],
  classic: [
    {
      target: ".field",
      clear: ".field-zone",
      title: "Play a card",
      text: "Drag a card from your hand onto an empty slot of the stack - or click it, then the slot. It works right away.",
      advanceOn: "play",
    },
    {
      target: INTENT,
      title: "Enemy intent",
      text: "The badge shows the enemy's next move. Hover a dotted term anywhere to see what it means.",
    },
    {
      target: ".end-turn-button",
      title: "End the turn",
      text: "Done playing? End the turn - your permanents work, then the enemy acts.",
      advanceOn: "end",
    },
  ],
};

const EDGE_PX = 12;
const GAP_PX = 14;
const RING_PAD_PX = 6;

// `plays` and `turns` count the cards played and turns ended so far - a step
// waiting for one moves on when its count goes up.
export function Tutorial({ mode, plays, turns }: { mode: TutorialMode; plays: number; turns: number }) {
  const steps = STEPS[mode];
  const [at, setAt] = useState({ step: 0, plays, turns });
  if (plays !== at.plays || turns !== at.turns) {
    const waiting = steps[at.step]?.advanceOn;
    const done = (waiting === "play" && plays > at.plays) || (waiting === "end" && turns > at.turns);
    setAt({ step: done ? at.step + 1 : at.step, plays, turns });
  }
  const step = steps[at.step];
  const finished = step === undefined;
  const ring = useRef<HTMLDivElement>(null);
  const bubble = useRef<HTMLDivElement>(null);

  // seen once it has been started - leaving the fight halfway counts too
  useEffect(() => rememberTutorialSeen(mode), [mode]);

  // Ring around the target, note above it (under it where there is no room
  // above), both re-placed every frame: the table moves - a hand card lifts,
  // the lines fill. Without its target the note waits mid-screen.
  useLayoutEffect(() => {
    if (finished) return;
    let frame = 0;
    const place = () => {
      const target = document.querySelector(step.target);
      const box = target?.getBoundingClientRect();
      const visible = !!box && box.width > 0 && box.height > 0;
      const r = ring.current;
      const b = bubble.current;
      if (r) {
        r.hidden = !visible;
        if (visible) {
          Object.assign(r.style, {
            left: `${box.left - RING_PAD_PX}px`,
            top: `${box.top - RING_PAD_PX}px`,
            width: `${box.width + 2 * RING_PAD_PX}px`,
            height: `${box.height + 2 * RING_PAD_PX}px`,
          });
        }
      }
      if (b) {
        const { width, height } = b.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        let left = (vw - width) / 2;
        let top = vh * 0.3 - height / 2;
        if (visible) {
          const around = (step.clear && document.querySelector(step.clear)?.getBoundingClientRect()) || box;
          left = box.left + box.width / 2 - width / 2;
          const above = Math.min(box.top - RING_PAD_PX, around.top) - GAP_PX - height;
          const below = Math.max(box.bottom + RING_PAD_PX, around.bottom) + GAP_PX;
          top = above >= EDGE_PX ? above : below + height <= vh - EDGE_PX ? below : EDGE_PX;
        }
        b.style.left = `${Math.max(EDGE_PX, Math.min(vw - width - EDGE_PX, left))}px`;
        b.style.top = `${Math.max(EDGE_PX, Math.min(vh - height - EDGE_PX, top))}px`;
      }
      frame = requestAnimationFrame(place);
    };
    place();
    return () => cancelAnimationFrame(frame);
  }, [finished, step]);

  if (finished) return null;
  const last = at.step === steps.length - 1;
  const next = () => {
    sfx.play("click");
    setAt({ step: at.step + 1, plays, turns });
  };
  const skip = () => {
    sfx.play("click");
    setAt({ step: steps.length, plays, turns });
  };
  // portalled like the help sheet: fixed to the window, not the panel
  return createPortal(
    <>
      <div ref={ring} className="coach-ring" aria-hidden="true" />
      <div ref={bubble} className="coach-bubble" role="region" aria-label="Tutorial">
        <div className="coach-head">
          <span className="coach-count">
            {at.step + 1}/{steps.length}
          </span>
          <b className="coach-title">{step.title}</b>
        </div>
        <p className="coach-text" aria-live="polite">
          <RichText text={step.text} />
        </p>
        <div className="coach-actions">
          <button type="button" className="coach-skip" onClick={skip}>
            Skip tutorial
          </button>
          <button type="button" className="coach-next" onClick={next}>
            {last ? "Got it" : "Next"}
          </button>
        </div>
      </div>
    </>,
    document.body,
  );
}
