import type { Character, CharacterView } from "../api";

export function CharacterPicker({
  characters,
  selected,
  onSelect,
  disabled,
}: {
  characters: CharacterView[];
  selected: Character;
  onSelect: (character: Character) => void;
  disabled: boolean;
}) {
  const current = characters.find((c) => c.id === selected) ?? characters[0];
  return (
    <div className="setting-picker character-picker">
      <p className="setting-picker-label">Choose who travels</p>
      <div className="choice-buttons">
        {characters.map((character) => (
          <button
            key={character.id}
            disabled={disabled}
            className={character.id === selected ? "is-selected" : undefined}
            onClick={() => onSelect(character.id)}
          >
            {character.name}
          </button>
        ))}
      </div>
      {current && (
        <p className="character-blurb">
          <span>{current.title}</span>
          {current.description}
        </p>
      )}
    </div>
  );
}
