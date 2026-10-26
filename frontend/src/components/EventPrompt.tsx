import type { PendingEventView } from "../api";
import { RichText } from "./RichText";

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
          <button
            key={option.index}
            className="event-option"
            disabled={disabled}
            onClick={() => onChoose(option.index)}
          >
            <span className="event-option-label">{option.label}</span>
            <span className="event-option-effects">
              <RichText text={option.effects} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
