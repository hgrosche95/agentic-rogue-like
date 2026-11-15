const PREFIX = "AGI:";

// One of the AGI's lines (or the part of it typed so far): "AGI:" in the
// pixel face, the words after it as they are - nothing the AGI says is a
// number or a card worth colouring.
export function AgiText({ text }: { text: string }) {
  if (!PREFIX.startsWith(text.slice(0, PREFIX.length))) return <>{text}</>;
  return (
    <>
      <b className="tok-agi">{text.slice(0, PREFIX.length)}</b>
      {text.slice(PREFIX.length)}
    </>
  );
}
