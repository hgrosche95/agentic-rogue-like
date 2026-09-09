import type { MapNode } from "../api";

const NODE_LABELS: Record<MapNode["type"], string> = {
  combat: "Fight",
  elite: "Elite fight",
  event: "Event",
  shop: "Shop",
  rest: "Rest",
  boss: "Boss",
};

export function NodeChoices({
  choices,
  onChoose,
  disabled,
}: {
  choices: MapNode[];
  onChoose: (nodeId: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="choice-buttons">
      {choices.map((node) => (
        <button key={node.id} disabled={disabled} onClick={() => onChoose(node.id)}>
          {NODE_LABELS[node.type]} (floor {node.floor})
        </button>
      ))}
    </div>
  );
}
