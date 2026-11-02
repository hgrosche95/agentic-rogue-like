import { useCallback, useEffect, useRef } from "react";
import type { Character, CharacterView } from "../api";
import type { Hero, PixelScene } from "../pixel/scene";
import { PixelStage } from "./PixelStage";
import { RichText } from "./RichText";

// The lab's own pixel scene, framed on whoever stands at the keyboard: the
// arena drawn once per traveller, cropped by CSS to the figure (see
// .character-portrait in flair.css). Picking one makes it act - the
// chosen traveller gets to work, the other one idles in the dark.
function CharacterPortrait({ hero, active }: { hero: Hero; active: boolean }) {
  const sceneRef = useRef<PixelScene | null>(null);
  const onScene = useCallback(
    (scene: PixelScene) => {
      sceneRef.current = scene;
      scene.setHero(hero);
    },
    [hero],
  );
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    scene.setStatus({ typing: active, block: 0, armor: 0, enemyBlock: 0, turrets: 0, amplifiers: 0, fortify: 0 });
    if (active) scene.trigger("draw_bonus", 120);
  }, [active]);
  return (
    <span className="character-portrait" aria-hidden="true">
      <span className="character-portrait-crop">
        <PixelStage fit="fill" onScene={onScene} />
      </span>
    </span>
  );
}

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
      <div className="choice-buttons character-cards">
        {characters.map((character) => (
          <button
            key={character.id}
            disabled={disabled}
            aria-pressed={character.id === selected}
            className={`character-card${character.id === selected ? " is-selected" : ""}`}
            onClick={() => onSelect(character.id)}
          >
            <CharacterPortrait hero={character.id} active={character.id === selected} />
            <span className="character-card-name">{character.name}</span>
          </button>
        ))}
      </div>
      {current && (
        <p className="character-blurb">
          <span>{current.title}</span>
          {/* one block, so the marked terms stay inline (direct spans are blocks here) */}
          <span>
            <RichText text={current.description} />
          </span>
        </p>
      )}
    </div>
  );
}
