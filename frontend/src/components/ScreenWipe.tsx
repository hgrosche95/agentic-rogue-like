import { useState } from "react";

// One motif for every change of screen: a scanline sweeps down over the new
// one, a trail of light behind it - the old frame overwritten line by line.
// Into and out of a fight is left out: the rift jump does those.
export function ScreenWipe({ kind }: { kind: string }) {
  // id 0: the first screen after loading, which has its own entrance
  const [shown, setShown] = useState({ kind, id: 0 });
  if (kind !== shown.kind) {
    const rift = (a: string, b: string) => a === "combat" || b === "combat";
    setShown({ kind, id: rift(shown.kind, kind) ? shown.id : shown.id + 1 });
  }
  return shown.id > 0 ? <div key={shown.id} className="screen-wipe" aria-hidden="true" /> : null;
}
