import type { Card } from "../api";
import { stackDeck } from "../deck";
import { CardFace } from "./CardFace";
import { CloseButton, Overlay } from "./Overlay";

// The whole deck, identical cards stacked into one tile with a count.
export function DeckView({ deck, onClose }: { deck: Card[]; onClose: () => void }) {
  return <PileView title="Your deck" cards={deck} onClose={onClose} />;
}

// A look into a pile of cards. `ordered`: shown as they lie, the latest
// first (the Graveyard, the Banished pile - what Undo or Undelete takes back is
// on top); otherwise identical cards stacked into one tile with a count.
export function PileView({
  title,
  cards,
  onClose,
  ordered = false,
  note,
}: {
  title: string;
  cards: Card[];
  onClose: () => void;
  ordered?: boolean;
  note?: string;
}) {
  const tiles = ordered
    ? [...cards].reverse().map((card, i) => ({ card, count: 1, key: `${card.id}-${i}` }))
    : stackDeck(cards).map(({ card, count }) => ({ card, count, key: card.name }));

  return (
    <Overlay label={title} onClose={onClose} className="deck-view">
      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">{title}</h2>
          <span className="panel-sub">
            {cards.length} card{cards.length === 1 ? "" : "s"}
            {note ? ` · ${note}` : ordered ? " · latest first" : ` · ${tiles.length} different`}
          </span>
          <CloseButton onClick={onClose} label={`Close ${title.toLowerCase()}`} />
        </div>
        {cards.length === 0 ? (
          <p className="muted pile-empty">Nothing here yet.</p>
        ) : (
          <div className="deck-grid">
            {tiles.map(({ card, count, key }, i) => (
              <div key={key} className={`hand-card deck-card type-${card.type}`}>
                <CardFace card={card} />
                {count > 1 && <span className="deck-count">×{count}</span>}
                {ordered && i === 0 && <span className="deck-count is-top">top</span>}
              </div>
            ))}
          </div>
        )}
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
