export function HistoryLog({ history }: { history: string[] }) {
  return (
    <div className="history-log">
      {history.length === 0 && <p className="muted">Nothing has happened yet.</p>}
      {history.map((line, i) => (
        <p key={i}>{line}</p>
      ))}
    </div>
  );
}
