import { createPortal } from "react-dom";
import { CloseButton, Overlay } from "./Overlay";
import { RichText } from "./RichText";

// The "i" next to the stack: how a fight works - above all program mode,
// whose rules nothing on the table explains by itself.
const PROGRAM_RULES: [string, string][] = [
  ["Queue", "Attacks, blocks, heals and Final Strike go into a line - nothing happens yet."],
  [
    "Run",
    "Run program runs the lines left to right, then the enemy acts. Above the lines you see what the program will do: the enemy's HP and block, your block.",
  ],
  [
    "Background",
    "Permanents don't take a line: they run in the background, as many as you play, and work on the whole program - an Overclock boosts every line.",
  ],
  ["Right away", "Draw, retrieve and other card-flow cards still work the moment you play them."],
  ["Move", "Drag a queued card onto another line - or click it, then the line. An occupied line swaps."],
  [
    "Control flow",
    "Fork: the next action runs twice. Loop: the last action to its left runs again. If Wounded: the next action runs twice if the enemy is at half HP or less by then. Vibe-Coder only - Pipe: the next action gets a bonus for every action that already ran. Batch: frees tokens for every action still to run.",
  ],
  [
    "Interrupt",
    "An enemy announcing an Interrupt lets only your first lines run - the cut ones are greyed out and go to the graveyard unused. Put what matters first.",
  ],
  [
    "Refactor",
    "A boss announcing a Refactor runs your program right to left this turn - Fork and Loop then steer the lines to their left.",
  ],
  ["Hot Path", "With the Hot Path artifact, the card in its gold line runs as its upgraded version."],
];

const CLASSIC_RULES: [string, string][] = [
  ["Play", "Drag a card onto an empty slot - or click it, then the slot. It works right away."],
  [
    "Permanents",
    "Permanent cards stay on the field. An Overclock boosts every slot to its right - the number on a slot shows what a card would do there.",
  ],
  ["Enemy", "The mark over the enemy shows its next move. End the turn and it acts."],
];

const SHARED_RULES: [string, string][] = [
  ["Hand", "Unplayed cards stay in your hand, up to its limit - over it, you discard when ending the turn."],
  [
    "Context",
    "Vibe-Coder only: cards cost tokens. Past the window they may hallucinate and backfire - a red outline marks a queued one that will.",
  ],
];

export function CombatHelp({ programMode, onClose }: { programMode: boolean; onClose: () => void }) {
  const rules = [...(programMode ? PROGRAM_RULES : CLASSIC_RULES), ...SHARED_RULES];
  // Portalled out of the combat panel: an ancestor there would otherwise
  // become the fixed backdrop's containing block, and it would scroll away.
  return createPortal(
    <Overlay label="How a fight works" onClose={onClose} className="combat-help">
      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">{programMode ? "Program mode" : "How a fight works"}</h2>
          <span className="panel-sub">{programMode ? "Your field is a program" : "Classic"}</span>
          <CloseButton onClick={onClose} label="Close help" />
        </div>
        <dl className="help-rules">
          {rules.map(([term, text]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>
                <RichText text={text} />
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </Overlay>,
    document.body,
  );
}

export function HelpButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="help-btn" aria-label="How a fight works" title="How a fight works" onClick={onClick}>
      i
    </button>
  );
}
