import { useState } from "react";

const SETTING_LABELS: Record<string, string> = {
  dungeon: "Dungeon",
  cyberpunk: "Cyberpunk",
  "alien planet": "Alien Planet",
  "pirate seas": "Pirate Seas",
  "haunted carnival": "Haunted Carnival",
};

const MAX_CUSTOM_SETTING_LENGTH = 40;

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
  const [isCustom, setIsCustom] = useState(false);
  const [customValue, setCustomValue] = useState("");

  function pickPreset(setting: string) {
    setIsCustom(false);
    onSelect(setting);
  }

  function pickCustom() {
    setIsCustom(true);
    onSelect(customValue);
  }

  function changeCustomValue(value: string) {
    setCustomValue(value);
    onSelect(value);
  }

  return (
    <div className="setting-picker">
      <p className="setting-picker-label">Pick a setting for the encounter agent</p>
      <div className="choice-buttons">
        {settings.map((setting) => (
          <button
            key={setting}
            disabled={disabled}
            className={!isCustom && setting === selected ? "is-selected" : undefined}
            onClick={() => pickPreset(setting)}
          >
            {SETTING_LABELS[setting] ?? setting}
          </button>
        ))}
        <button
          disabled={disabled}
          className={isCustom ? "is-selected" : undefined}
          onClick={pickCustom}
        >
          Custom...
        </button>
      </div>
      {isCustom && (
        <input
          className="custom-setting-input"
          type="text"
          placeholder="e.g. underwater steampunk city"
          maxLength={MAX_CUSTOM_SETTING_LENGTH}
          value={customValue}
          disabled={disabled}
          onChange={(e) => changeCustomValue(e.target.value)}
          autoFocus
        />
      )}
    </div>
  );
}
