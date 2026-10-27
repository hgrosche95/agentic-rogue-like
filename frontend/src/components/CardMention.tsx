import { useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Card } from "../api";
import { CardFace } from "./CardFace";
import { RichText } from "./RichText";

// A card's name in running text that shows the card itself on hover.
export function CardMention({ card, children }: { card: Card; children?: ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [at, setAt] = useState<{ x: number; y: number; below: boolean } | null>(null);
  return (
    <span
      ref={ref}
      className="card-mention"
      onPointerEnter={() => {
        const box = ref.current?.getBoundingClientRect();
        // a card is tall: near the top of the screen it opens downwards
        const below = !!box && box.top < 240;
        if (box) setAt({ x: box.left + box.width / 2, y: below ? box.bottom : box.top, below });
      }}
      onPointerLeave={() => setAt(null)}
    >
      {children ?? card.name}
      {at &&
        createPortal(
          <div className={`card-preview${at.below ? " is-below" : ""}`} style={{ left: at.x, top: at.y }}>
            <div className={`hand-card reward-card type-${card.type} rarity-${card.rarity}`}>
              <CardFace card={card} />
            </div>
          </div>,
          document.body,
        )}
    </span>
  );
}

// `text` with the named cards hoverable (CardMention) and game terms marked.
export function TextWithCards({ text, cards }: { text: string; cards: Card[] }) {
  const byName = new Map(cards.map((c) => [c.name, c]));
  // an upgraded card ("Exploit+") also answers to its plain name, the way a
  // Hotfix deal names what it will upgrade
  for (const card of cards) {
    const plain = card.name.replace(/\+$/, "");
    if (!byName.has(plain)) byName.set(plain, card);
  }
  const names = [...byName.keys()].sort((a, b) => b.length - a.length);
  if (names.length === 0) return <RichText text={text} />;
  const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pieces = text.split(new RegExp(`(${escaped.join("|")})`));
  return (
    <>
      {pieces.map((piece, i) => {
        const card = byName.get(piece);
        return card ? (
          <CardMention key={i} card={card}>
            {piece}
          </CardMention>
        ) : (
          <RichText key={i} text={piece} />
        );
      })}
    </>
  );
}
