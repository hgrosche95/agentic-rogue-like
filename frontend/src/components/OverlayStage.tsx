import { Children, cloneElement, isValidElement, useEffect, useRef, useState, type ReactElement, type ReactNode } from "react";
import { OverlayStageContext, stageTimings, type Pick, type StagePhase } from "../overlayStage";

// The run's choice windows, one after another (artifact, kit, the AGI's deal,
// rewards, rooms): instead of swapping at once, the window folds shut around
// the pick while the request runs, holds on a seam until the answer is in,
// and the next one opens out of it - or the backdrop fades onto the map.
// Children are the candidate <Overlay>s, each with a key naming the window;
// the last one rendered is the one on top, so the one to show.
export function OverlayStage({ busy, children }: { busy: boolean; children: ReactNode }) {
  const target = Children.toArray(children).filter(isValidElement).at(-1) ?? null;
  const [shown, setShown] = useState<ReactElement | null>(target);
  const [picked, setPicked] = useState<Pick | null>(null);
  const [closingSince, setClosingSince] = useState<number | null>(null);

  const targetId = target?.key ?? null;
  const switching = targetId !== (shown?.key ?? null);
  // The same window with new data (a purchase in the shop), or a first one
  // over the map: nothing to close, show it as it is.
  // (toArray copies the elements on every call, their props stay the same)
  if (target !== null && target.props !== shown?.props && (shown === null || !switching)) setShown(target);
  // The request failed and the window stays up: take the pick back.
  if (!busy && !switching && picked !== null) {
    setPicked(null);
    setClosingSince(null);
  }

  // the window to open once the wait is over - its element changes with
  // every render, the wait shouldn't restart with it
  const latest = useRef(target);
  useEffect(() => {
    latest.current = target;
  });

  useEffect(() => {
    if (!switching) return;
    const { closeMs, beatMs, leaveMs } = stageTimings();
    const elapsed = closingSince === null ? 0 : performance.now() - closingSince;
    const wait = Math.max(closeMs - elapsed, targetId === null ? leaveMs : 0) + beatMs;
    const timer = window.setTimeout(() => {
      setShown(latest.current);
      setPicked(null);
      setClosingSince(null);
    }, wait);
    return () => window.clearTimeout(timer);
  }, [switching, targetId, closingSince]);

  if (shown === null) return null;
  const phase: StagePhase = switching ? (targetId === null ? "leaving" : "closing") : picked !== null ? "closing" : "open";
  const view = switching || target === null ? shown : target;
  const pick = (choice: Pick) => {
    setPicked(choice);
    setClosingSince(performance.now());
  };
  return (
    <OverlayStageContext.Provider value={{ id: String(view.key), phase, picked, pick }}>
      {/* one key for every window, so the backdrop stays put between them */}
      {cloneElement(view, { key: "stage" })}
    </OverlayStageContext.Provider>
  );
}
