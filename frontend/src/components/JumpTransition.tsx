import { useEffect, useRef, useState } from "react";
import type { NodeType } from "../api";
import { sfx } from "../audio";
import { NODE_STYLE } from "../nodeTypes";

// The jump to the next layer, like a ship dropping out of FTL: light streaks
// rush past, a glitch wipes the screen and the new layer's path types itself
// in. Plays whenever the run goes one layer deeper (or into the next act) -
// never on load. Over in under a second and never in the way: it takes no
// clicks, and with reduced motion it is only the path, faded in and out.
const JUMP_MS = 1150;

export function JumpTransition({ stamp, layer, room }: { stamp: string; layer: string; room: NodeType }) {
  const seen = useRef(stamp);
  const [jump, setJump] = useState<{ id: string; layer: string; room: NodeType } | null>(null);
  useEffect(() => {
    if (seen.current === stamp) return;
    seen.current = stamp;
    setJump({ id: stamp, layer, room });
    sfx.play("jump");
    const timer = window.setTimeout(() => setJump(null), JUMP_MS);
    return () => window.clearTimeout(timer);
  }, [stamp, layer, room]);
  if (!jump) return null;
  return (
    <div key={jump.id} className="jump-transition" aria-hidden="true">
      <span className="jump-streaks" />
      <span className="jump-wipe" />
      <span className="jump-label">
        <b>{jump.layer}</b>
        <small>{NODE_STYLE[jump.room].label}</small>
      </span>
    </div>
  );
}
