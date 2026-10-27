import { useContext, useEffect, type ReactNode } from "react";
import { OverlayStageContext } from "../overlayStage";

// A window over the current screen: the screen stays where it is, dimmed
// behind it, instead of the content being pushed around. The top bar stays
// above the backdrop, so deck, map and audio are reachable during a choice.
// Choices the run can't go on without (a reward, an event) pass no onClose.
// Inside an OverlayStage the window opens and folds shut with the stage.
export function Overlay({
  children,
  onClose,
  label,
  className = "",
}: {
  children: ReactNode;
  onClose?: () => void;
  label: string;
  className?: string;
}) {
  useEffect(() => {
    if (!onClose) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const stage = useContext(OverlayStageContext);

  return (
    <div
      className={`overlay-backdrop${stage?.phase === "leaving" ? " is-leaving" : ""}`}
      onClick={(event) => {
        if (onClose && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        key={stage?.id}
        className={`overlay-window ${className}${stage ? ` is-staged is-${stage.phase}` : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={label}
      >
        {children}
      </div>
      {/* what's left of a folded window while the next one is on its way */}
      {stage && stage.phase !== "open" && <span className="overlay-seam" aria-hidden="true" />}
    </div>
  );
}

export function CloseButton({ onClick, label = "Close" }: { onClick: () => void; label?: string }) {
  return (
    <button type="button" className="icon-btn is-small" aria-label={label} onClick={onClick}>
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <line className="close-icon" x1="3" y1="3" x2="13" y2="13" />
        <line className="close-icon" x1="13" y1="3" x2="3" y2="13" />
      </svg>
    </button>
  );
}
