// Classic play, or the field as a program (see the backend's combat.run_program):
// actions queue into lines and run left to right at the end of the turn.
const MODES = [
  {
    program: false,
    label: "Classic",
    hint: "Every card resolves the moment you play it.",
  },
  {
    program: true,
    label: "Program",
    hint: "Attacks, blocks and heals queue into lines and run left to right at the end of the turn - order them, and steer them with Fork, Loop and If Wounded.",
  },
];

export function ModePicker({
  program,
  onSelect,
  disabled,
}: {
  program: boolean;
  onSelect: (program: boolean) => void;
  disabled: boolean;
}) {
  const selected = MODES.find((mode) => mode.program === program) ?? MODES[0];
  return (
    <div className="setting-picker mode-picker">
      <p className="setting-picker-label">Pick a mode</p>
      <div className="choice-buttons">
        {MODES.map((mode) => (
          <button
            key={mode.label}
            disabled={disabled}
            className={mode.program === program ? "is-selected" : undefined}
            onClick={() => onSelect(mode.program)}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <p className="mode-hint">{selected.hint}</p>
    </div>
  );
}
