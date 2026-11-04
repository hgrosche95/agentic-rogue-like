import type { PendingEventView } from "../api";
import { pickClass, useOverlayPick } from "../overlayStage";
import { RichText } from "./RichText";
import { RoomHeader } from "./RoomHeader";

export function EventPrompt({
  event,
  onChoose,
  disabled,
  where,
}: {
  event: PendingEventView;
  onChoose: (optionIndex: number) => void;
  disabled: boolean;
  // the layer it happens in, for the terminal line over it
  where?: string;
}) {
  const { picked, pick } = useOverlayPick();
  return (
    <div className="event-prompt">
      <RoomHeader kind="event" line={where ? `anomaly detected in ${where}` : "anomaly detected"} />
      <p>{event.description}</p>
      <div className="choice-buttons">
        {event.options.map((option) => (
          <button
            key={option.index}
            className={`event-option${pickClass(picked, option.index)}`}
            disabled={disabled}
            onClick={() => {
              pick(option.index);
              onChoose(option.index);
            }}
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
