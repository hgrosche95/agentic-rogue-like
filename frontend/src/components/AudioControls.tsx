import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { getSettings, sfx, subscribeSettings, updateSettings } from "../audio";

// Mute toggle plus a small panel with separate music and effects volume.
export function AudioControls({ className = "" }: { className?: string }) {
  const settings = useSyncExternalStore(subscribeSettings, getSettings);
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [isOpen]);

  return (
    <div className={`audio-controls ${className}`} ref={rootRef}>
      <button
        type="button"
        className={`icon-btn${settings.muted ? " is-muted" : ""}`}
        aria-label={settings.muted ? "Unmute sound" : "Mute sound"}
        aria-pressed={settings.muted}
        onClick={() => updateSettings({ muted: !settings.muted })}
      >
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path className="dial" d="M3 8 h3 l4 -3.5 v11 l-4 -3.5 h-3 z" />
          {settings.muted ? (
            <>
              <line className="close-icon" x1="13" y1="7.5" x2="18" y2="12.5" />
              <line className="close-icon" x1="18" y1="7.5" x2="13" y2="12.5" />
            </>
          ) : (
            <>
              <path className="needle" d="M12.6 7.6 a3.4 3.4 0 0 1 0 4.8" fill="none" />
              <path className="needle" d="M14.8 5.4 a6.5 6.5 0 0 1 0 9.2" fill="none" />
            </>
          )}
        </svg>
      </button>
      <button
        type="button"
        className="icon-btn"
        aria-label="Volume settings"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((open) => !open)}
      >
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <line className="dial" x1="4" y1="6" x2="16" y2="6" />
          <line className="dial" x1="4" y1="14" x2="16" y2="14" />
          <circle className="needle knob" cx={4 + settings.music * 12} cy="6" r="1.8" />
          <circle className="needle knob" cx={4 + settings.sfx * 12} cy="14" r="1.8" />
        </svg>
      </button>
      {isOpen && (
        <div className="audio-panel" role="group" aria-label="Volume">
          <label>
            <span>Music</span>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(settings.music * 100)}
              onChange={(event) => updateSettings({ music: Number(event.target.value) / 100 })}
            />
            <span className="audio-value">{Math.round(settings.music * 100)}</span>
          </label>
          <label>
            <span>Effects</span>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(settings.sfx * 100)}
              onChange={(event) => updateSettings({ sfx: Number(event.target.value) / 100 })}
              // a sample of the new level once the slider is let go
              onPointerUp={() => sfx.play("select")}
              onKeyUp={() => sfx.play("select")}
            />
            <span className="audio-value">{Math.round(settings.sfx * 100)}</span>
          </label>
          {settings.muted && <p className="audio-muted-hint">Sound is muted.</p>}
        </div>
      )}
    </div>
  );
}
