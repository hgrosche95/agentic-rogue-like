import { useMemo, useState } from "react";
import { loadBestiary, type BestiaryEntry } from "../bestiary";
import { SETTING_LABELS } from "../settings";
import { CloseButton, Overlay } from "./Overlay";
import { PixelEnemy } from "./PixelEnemy";
import "../bestiary.css";

// The bestiary (bestiary.ts): every enemy met, across runs, as a grid of
// sprites - filterable by setting, with a page for each one.

const settingKey = (setting: string) => setting.trim().toLowerCase();
const settingLabel = (setting: string) => SETTING_LABELS[settingKey(setting)] ?? setting;

function EnemySprite({ entry, scale }: { entry: BestiaryEntry; scale: number }) {
  return (
    <PixelEnemy
      className="bestiary-sprite"
      scale={scale}
      spec={{
        name: entry.name,
        maxHp: entry.maxHp,
        attack: entry.attack,
        setting: entry.setting,
        bodyShape: entry.bodyShape ?? undefined,
        feature: entry.feature ?? undefined,
        finalBoss: entry.finalBoss,
      }}
    />
  );
}

function EntryPage({ entry, onBack }: { entry: BestiaryEntry; onBack: () => void }) {
  return (
    <div className="bestiary-page">
      <button type="button" className="bestiary-back" onClick={onBack}>
        ← All enemies
      </button>
      <div className="bestiary-page-body">
        <div className="bestiary-page-art">
          <EnemySprite entry={entry} scale={3} />
        </div>
        <div className="bestiary-page-text">
          <h3 className="bestiary-page-name">{entry.name}</h3>
          <span className="bestiary-setting">{settingLabel(entry.setting)}</span>
          {entry.description && <p className="bestiary-description">{entry.description}</p>}
          <dl className="bestiary-stats">
            <div>
              <dt>Max HP</dt>
              <dd>{entry.maxHp}</dd>
            </div>
            <div>
              <dt>Attack</dt>
              <dd>{entry.attack}</dd>
            </div>
            <div>
              <dt>Met</dt>
              <dd>{entry.encounters}×</dd>
            </div>
            <div>
              <dt>Defeated</dt>
              <dd>{entry.defeated}×</dd>
            </div>
            <div className={entry.kills > 0 ? "is-deadly" : undefined}>
              <dt>Killed you</dt>
              <dd>{entry.kills}×</dd>
            </div>
          </dl>
          {entry.moves.length > 0 && (
            <>
              <h4 className="bestiary-moves-title">Moves seen</h4>
              <ul className="bestiary-moves">
                {entry.moves.map((move) => (
                  <li key={move}>{move}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function BestiaryView({ currentSetting, onClose }: { currentSetting: string; onClose: () => void }) {
  // read once when it opens - nothing is recorded while it is up
  const [entries] = useState(() => [...loadBestiary()].sort((a, b) => b.lastSeen - a.lastSeen));
  const settings = useMemo(() => {
    const seen = new Map<string, string>();
    for (const e of entries) if (!seen.has(settingKey(e.setting))) seen.set(settingKey(e.setting), e.setting);
    return [...seen.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [entries]);
  // open on this run's world when it has entries, else on all of them
  const [filter, setFilter] = useState<string>(() =>
    entries.some((e) => settingKey(e.setting) === settingKey(currentSetting)) && settings.length > 1
      ? settingKey(currentSetting)
      : "all",
  );
  const [selected, setSelected] = useState<BestiaryEntry | null>(null);
  const shown = filter === "all" ? entries : entries.filter((e) => settingKey(e.setting) === filter);

  return (
    <Overlay label="Bestiary" onClose={onClose} className="is-wide bestiary-view">
      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Bestiary</h2>
          <span className="panel-sub">
            {entries.length} enem{entries.length === 1 ? "y" : "ies"} met
          </span>
          <CloseButton onClick={onClose} label="Close bestiary" />
        </div>
        {entries.length === 0 ? (
          <p className="muted bestiary-empty">
            No enemies met yet. Every enemy you fight is recorded here, across runs.
          </p>
        ) : selected ? (
          <EntryPage entry={selected} onBack={() => setSelected(null)} />
        ) : (
          <>
            {settings.length > 1 && (
              <div className="bestiary-filter" role="group" aria-label="Filter by setting">
                <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
                  All
                </button>
                {settings.map(([key, setting]) => (
                  <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>
                    {settingLabel(setting)}
                  </button>
                ))}
              </div>
            )}
            <div className="bestiary-grid">
              {shown.map((entry) => (
                <button
                  key={`${settingKey(entry.setting)}|${entry.name}`}
                  type="button"
                  className={`bestiary-tile${entry.kills > 0 ? " is-deadly" : ""}`}
                  onClick={() => setSelected(entry)}
                  aria-label={`${entry.name}, ${settingLabel(entry.setting)}`}
                >
                  <span className="bestiary-tile-art">
                    <EnemySprite entry={entry} scale={2} />
                  </span>
                  <span className="bestiary-tile-name">{entry.name}</span>
                  <span className="bestiary-tile-counts">
                    <span>{entry.defeated} beaten</span>
                    {entry.kills > 0 && (
                      <span className="bestiary-kills">
                        {entry.kills} kill{entry.kills === 1 ? "" : "s"}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </section>
    </Overlay>
  );
}

export function BestiaryButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="icon-btn" aria-label="Show bestiary" onClick={onClick}>
      <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
        <rect className="dial" x="4" y="3" width="12" height="14" rx="1.5" />
        <line className="dial" x1="7" y1="3" x2="7" y2="17" />
        <circle className="needle" cx="11.5" cy="9" r="2" />
      </svg>
    </button>
  );
}
