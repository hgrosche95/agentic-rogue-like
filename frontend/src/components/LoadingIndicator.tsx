import { useEffect, useState } from "react";

// Shown only once a request has taken a moment, so quick ones don't flash it.
const SHOW_AFTER_MS = 300;
// Past this, say why it might take a while: the API scales to zero when
// idle and the first request has to wait for it to start, and generated
// enemies/narration are LLM calls.
const SLOW_AFTER_MS = 5000;

export function LoadingIndicator({ active, label }: { active: boolean; label: string }) {
  const [phase, setPhase] = useState<"hidden" | "shown" | "slow">("hidden");

  useEffect(() => {
    if (!active) return;
    const show = window.setTimeout(() => setPhase("shown"), SHOW_AFTER_MS);
    const slow = window.setTimeout(() => setPhase("slow"), SLOW_AFTER_MS);
    return () => {
      window.clearTimeout(show);
      window.clearTimeout(slow);
      setPhase("hidden");
    };
  }, [active]);

  if (!active || phase === "hidden") return null;
  return (
    <div className="loading-indicator" role="status" aria-live="polite">
      <span className="loading-spinner" aria-hidden="true" />
      <span>
        {label}
        {phase === "slow" && <span className="loading-slow"> Still working - the server may be waking up.</span>}
      </span>
    </div>
  );
}
