const SETTING_LABELS: Record<string, string> = {
  dungeon: "Dungeon",
  cyberpunk: "Cyberpunk",
  "alien planet": "Alien Planet",
  "pirate seas": "Pirate Seas",
  "haunted carnival": "Haunted Carnival",
};

export function SettingPicker({
  settings,
  selected,
  onSelect,
  disabled,
}: {
  settings: string[];
  selected: string;
  onSelect: (setting: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="setting-picker">
      <p className="setting-picker-label">Pick a setting for the encounter agent</p>
      <div className="choice-buttons">
        {settings.map((setting) => (
          <button
            key={setting}
            disabled={disabled}
            className={setting === selected ? "is-selected" : undefined}
            onClick={() => onSelect(setting)}
          >
            {SETTING_LABELS[setting] ?? setting}
          </button>
        ))}
      </div>
    </div>
  );
}
