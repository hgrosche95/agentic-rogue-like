import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { sfx } from "../audio";
import { type Banner } from "../banners";
import { tempoMs } from "../tempo";

// The fight's punctuation: a short banner over the rift when the turn
// changes hands or a boss overclocks, and a full-width band when a boss
// walks on. Banners never take the pointer and sit between the monitor and
// the beams, so they don't hide a hit; the intro band holds the screen for a
// couple of seconds and gives way to any click or key.

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function TurnBanner({ banner }: { banner: Banner }) {
  useEffect(() => {
    sfx.play(banner.kind === "player" ? "turn_start" : banner.kind === "enemy" ? "enemy_turn" : "boss_phase");
  }, [banner]);
  return (
    <div
      className={`turn-banner is-${banner.kind}`}
      style={{ "--banner-ms": `${banner.ms}ms` } as CSSProperties}
      role="status"
      aria-live="polite"
    >
      <span className="turn-banner-band" aria-hidden="true" />
      <span className="turn-banner-title" data-text={banner.title}>
        {banner.title}
      </span>
      {banner.sub && <span className="turn-banner-sub">{banner.sub}</span>}
    </div>
  );
}

// how long the band holds before it lets go, and how long letting go takes -
// with reduced motion the band is gone the instant it lets go
const INTRO_MS = 2000;
const INTRO_REDUCED_MS = 2000;
const OUTRO_MS = 320;

// A boss walks on: one hard-edged band across the whole viewport with the
// boss's name in Silkscreen, its description underneath, and the fixed
// "Core AI" line below that.
export function BossIntro({
  name,
  description,
  finalBoss,
  onDone,
}: {
  name: string;
  description: string;
  finalBoss: boolean;
  onDone: () => void;
}) {
  const [leaving, setLeaving] = useState(false);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });

  useEffect(() => {
    sfx.play("boss_intro");
  }, []);

  // hold, then let go - sooner on a click or key
  useEffect(() => {
    const reduced = reducedMotion();
    if (leaving) {
      const timer = window.setTimeout(() => done.current(), tempoMs(reduced ? 0 : OUTRO_MS));
      return () => window.clearTimeout(timer);
    }
    const timer = window.setTimeout(
      () => setLeaving(true),
      tempoMs(reduced ? INTRO_REDUCED_MS : INTRO_MS),
    );
    // Space, Enter and Esc skip it - and go no further, or Space would end
    // the turn underneath (capture phase, ahead of the table's own keys)
    const onKey = (event: KeyboardEvent) => {
      if (![" ", "Enter", "Escape"].includes(event.key)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      setLeaving(true);
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey, { capture: true });
    };
  }, [leaving]);

  return createPortal(
    <div
      className={`boss-intro${finalBoss ? " is-final" : ""}${leaving ? " is-leaving" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-label={`${name} - boss`}
      onClick={() => setLeaving(true)}
    >
      <span className="boss-intro-scan" aria-hidden="true" />
      <div className="boss-intro-band">
        <h2 className="boss-intro-name" data-text={name}>
          {name}
        </h2>
        <p className="boss-intro-desc">{description}</p>
        <span className="boss-intro-core">Core AI</span>
      </div>
      <span className="boss-intro-skip">Click or Space to skip</span>
    </div>,
    document.body,
  );
}
