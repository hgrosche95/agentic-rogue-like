import type { PendingEventView } from "../api";

export function EventPrompt({
  event,
  onChoose,
  disabled,
}: {
  event: PendingEventView;
  onChoose: (optionIndex: number) => void;
  disabled: boolean;
}) {
  return (
    <div className="event-prompt">
      <p>{event.description}</p>
      <div className="choice-buttons">
        {event.options.map((option) => (
          <button key={option.index} disabled={disabled} onClick={() => onChoose(option.index)}>
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
