import type { Card } from "../api";
import { stackDeck } from "../deck";
import { CardFace } from "./CardFace";
import { CloseButton, Overlay } from "./Overlay";

// The whole deck, identical cards stacked into one tile with a count.
export function DeckView({ deck, onClose }: { deck: Card[]; onClose: () => void }) {
  const sorted = stackDeck(deck);

  return (
    <Overlay label="Your deck" onClose={onClose} className="deck-view">
      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Your deck</h2>
          <span className="panel-sub">
            {deck.length} cards · {sorted.length} different
          </span>
          <CloseButton onClick={onClose} label="Close deck" />
        </div>
        <div className="deck-grid">
          {sorted.map(({ card, count }) => (
            <div key={card.name} className={`hand-card deck-card type-${card.type}`}>
              <CardFace card={card} />
              {count > 1 && <span className="deck-count">×{count}</span>}
            </div>
          ))}
        </div>
      </section>
    </Overlay>
  );
}

export function DeckButton({ count, onClick }: { count: number; onClick: () => void }) {
  return (
    <button type="button" className="icon-btn deck-button" aria-label={`Show deck (${count} cards)`} onClick={onClick}>
      <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
        <rect className="dial" x="7" y="3" width="9" height="12" rx="1.5" />
        <rect className="dial" x="4" y="5.5" width="9" height="12" rx="1.5" />
      </svg>
      <span className="deck-button-count">{count}</span>
    </button>
  );
}
