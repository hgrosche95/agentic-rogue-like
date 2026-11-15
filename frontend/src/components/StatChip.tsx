import { useEffect, useState } from "react";

export type ChipIcon = "block" | "armor" | "malware" | "exposed" | "throttled";

function ChipGlyph({ icon }: { icon: ChipIcon }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="chip-icon">
      {icon === "block" && <path d="M10 2.6 16 5v4.4c0 4-2.7 6.6-6 8-3.3-1.4-6-4-6-8V5Z" />}
      {icon === "armor" && (
        <>
          <path d="M3.5 5.5h13v4c0 3.6-2.8 6.2-6.5 7.5-3.7-1.3-6.5-3.9-6.5-7.5Z" />
          <path d="M10 5.5V17M3.5 9.5h13" />
        </>
      )}
      {icon === "malware" && (
        <>
          <circle cx="10" cy="10" r="3.2" />
          <path d="M10 2.5v4M10 13.5v4M2.5 10h4M13.5 10h4M4.7 4.7l2.4 2.4M12.9 12.9l2.4 2.4M15.3 4.7l-2.4 2.4M7.1 12.9l-2.4 2.4" />
        </>
      )}
      {icon === "exposed" && (
        <>
          <path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10Z" />
          <circle cx="10" cy="10" r="2.4" />
        </>
      )}
      {icon === "throttled" && (
        <>
          <path d="M3.5 14a7 7 0 1 1 13 0" />
          <path d="M10 13.5 6.5 8.5" />
        </>
      )}
    </svg>
  );
}

// A chip for a number that comes and goes: an icon and the value, which
// pops when it grows and ticks down when it shrinks. Gone to zero, it stays
// a moment to break apart (`is-breaking`) instead of just vanishing.
const BREAK_MS = 520;

export function StatChip({
  className,
  icon,
  label,
  value,
  tip,
  tipTerm,
}: {
  className: string;
  icon: ChipIcon;
  label: string;
  value: number;
  tip?: string;
  tipTerm?: string;
}) {
  const [last, setLast] = useState(value);
  const [change, setChange] = useState<{ dir: "up" | "down"; id: number; from: number } | null>(null);
  if (value !== last) {
    // derived during render: the change since the last value
    setLast(value);
    setChange({ dir: value > last ? "up" : "down", id: (change?.id ?? 0) + 1, from: last });
  }
  const breaking = value <= 0 && change?.dir === "down";
  // the change whose break has played out
  const [brokenId, setBrokenId] = useState(0);
  const changeId = change?.id ?? 0;
  useEffect(() => {
    if (!breaking) return;
    const timer = window.setTimeout(() => setBrokenId(changeId), BREAK_MS);
    return () => window.clearTimeout(timer);
  }, [breaking, changeId]);
  const gone = brokenId === changeId;
  if (value <= 0 && (!breaking || gone)) return null;
  const shown = breaking ? (change?.from ?? 0) : value;
  return (
    <span
      key={change?.id ?? 0}
      className={`${className} stat-chip${change ? ` is-${change.dir}` : ""}${breaking ? " is-breaking" : ""}`}
      tabIndex={tip ? 0 : undefined}
      data-tip={tip}
      data-tip-term={tipTerm}
    >
      <ChipGlyph icon={icon} />
      {label} <b>{shown}</b>
    </span>
  );
}
