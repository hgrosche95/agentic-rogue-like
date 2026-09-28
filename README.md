# agentic-rogue-like

Ein Roguelike (Slay the Spire / FTL lassen grüßen), bei dem der Run-Inhalt
nicht aus einer festen Drop-Tabelle kommt, sondern live von einem LLM-Agenten
generiert wird — eingeschränkt auf Tool-Calls mit einem Balance-Budget, damit
er kreativ sein kann, ohne den Run kaputt zu machen.

## Ziel

Ein privates Projekt, um echte, praktische Erfahrung mit Agentic AI in Python
aufzubauen — LangGraph, Tool-Calling, Validierung strukturierter Ausgaben —
als Ergänzung zu meinem bisherigen TypeScript/NestJS-Agenten-Projekt
([ai-trip-planer](https://github.com/hgrosche95/ai-trip-planer)). Der Code
ist so geschrieben, dass er verstanden und erklärt werden kann, nicht nur
funktioniert: Das deterministische Spiel und die Agenten-Schicht sind bewusst
strikt getrennt, damit die Grenze zwischen "was die KI entscheiden darf" und
"was feste Spiellogik bleibt" sichtbar bleibt, statt zu verschwimmen.

## Screenshots

| Intro | Karte | Kampf |
| --- | --- | --- |
| ![Story-Intro mit Dr. Chronos und der Nachricht der AGI](docs/screenshots/intro.png) | ![Dungeon-Karte](docs/screenshots/map.png) | ![Kampf in der Arena gegen einen prozedural gezeichneten Gegner](docs/screenshots/combat.png) |

## Status

- [x] **Skelett** — Projekt-Setup, Kern-Datenmodelle (`RunState`,
      `PlayerState`, `MapNode`, `Enemy`)
- [x] **Deterministischer Kern-Loop** — prozedural generierte Node-Map,
      Kampf-/Event-/Rest-/Shop-Auflösung, Sieg-/Niederlage-Bedingungen.
      Vollständig spielbar im Terminal, noch ohne LLM.
- [x] **Web-UI + HTTP-API** — eine FastAPI-Schicht (`api.py`) legt dieselbe
      Engine über zustandslose HTTP-Requests offen (Zustand pro Run liegt in
      `sessions.py`), ein React/Vite-Frontend (`frontend/`) spielt einen Run
      als klickbare Dungeon-Map statt im Terminal. Ergänzt die CLI, ersetzt
      sie nicht — `cli.py` funktioniert unverändert weiter. Deployment nach
      Azure (Container Apps + Static Web Apps) via GitHub Actions.
- [x] **Arena und Story** — ein kurzes Story-Intro beim ersten Besuch
      (überspringbar, auf dem Startbildschirm wiederholbar); gekämpft wird
      in einer Arena aus einer Blender-Szene, in der Dr. Chronos seine
      Angriffe an einer Tastatur einhackt. Weil die Gegner erst zur Laufzeit
      entstehen, zeichnet `EnemyMonster.tsx` jeden als SVG aus Name (Seed),
      Max-HP (Größe), Angriff (Stacheln, Zähne) und Setting (Farben, Motiv).
- [x] **Kartenbasierter Kampf** — kein Energie-System; das Feld mit 5 Slots
      ist die Ressource. Aktionskarten (Exploit, Firewall, Hotfix, Kernel Panic)
      brauchen einen freien Slot, wirken sofort und wandern in den
      Friedhof; permanente Karten (Overclock, Encryption, Garbage Collector,
      Prefetch) belegen ihren Slot dauerhaft und wirken positionsabhängig — z. B.
      "Aktionskarten rechts von mir sind 25% effektiver". Nicht gespielte
      Handkarten bleiben für die nächste Runde erhalten statt zu verfallen.
      `cli.py` und die Tests spielen automatisiert (`auto_resolve_combat` —
      erste bezahlbare Karte in den ersten freien Slot, dann Rundenende),
      das Web-UI interaktiv Karte für Karte über eigene Endpunkte
      (`/combat/play-card`, `/combat/end-turn`).
- [x] **Deck-Building** — nach jedem Sieg eine von drei Karten wählen
      (`/runs/{id}/card-reward`); 17 Belohnungskarten mit Abwurfkosten,
      Einmal-Karten, Friedhof-/Verbannt-Mechaniken und neuen Permanenten.
- [x] **Effekte und Game Feel** — `frontend/src/fx/` leitet aus jeder
      Serverantwort (HP-/Hand-/Feld-Diff plus die neuen Log-Zeilen) Effekte
      ab: Screen-Shake nach Schaden skaliert (stark bei Kernel Panic und
      Boss-Treffern), Glitch-Projektile und Hit-Flashes, DDoS als
      Mehrfachtreffer mit Kombo-Anzeige, Zero-Day als Strahl, Botnet-Drohnen
      aus den Permanenten, Kernel Panic als Bluescreen mit zerfallenden
      Karten, Hex-Firewall (splittert, wenn sie einen Treffer schluckt),
      grüner Code beim Heilen, rot/blau/grüne Schadenszahlen, Karten, die
      sichtbar aus Deck, Friedhof oder Verbannt-Stapel in die Hand fliegen,
      sich auflösende Einmal-Karten, bootende Permanente, feuernde Daemons,
      Mainframe-Block, aufdeckende Belohnungskarten sowie Übergänge für
      Kampfstart, Gegner-Tod, Sieg und Niederlage. Nur CSS, SVG, Canvas und
      Web Animations API; bei `prefers-reduced-motion` entfallen Shake,
      Blitze und Partikel.
- [ ] **Encounter-Agent** — ein LangGraph-Agent, der Gegner über constrained
      Tool-Calls generiert und gegen ein Etagen-Budget validiert, mit
      Retry-Schleife bei Budget-Verstoß. Für Gegner voll eingeklinkt: die
      Engine ruft ihn über `ENCOUNTER_AGENT_ENABLED=1` live an und fällt bei
      jedem Fehler (API nicht erreichbar, Budget nach 3 Versuchen nie
      getroffen, ...) auf den statischen Pool zurück — in einem echten Lauf
      bereits beobachtet und mit `monkeypatch` deterministisch getestet.
      Relikte und Events als weitere Content-Typen fehlen noch.
- [x] **Encounter-Agent-Destillation** — Groqs Cloud-Call (`openai/gpt-oss-20b`)
      lässt sich per `ENCOUNTER_AGENT_MODEL_SOURCE=ollama` gegen ein selbst
      fein-getuntes Qwen2.5-1.5B tauschen, lokal per Ollama serviert, kein
      API-Key/Netz/Tageslimit nötig. Drei Trainingsläufe, volle Auswertung
      gegen die Groq-Baseline (Gültigkeit, Budget-Treue, Diversität,
      Kosten/Latenz) in [`training/RESULTS.md`](training/RESULTS.md) — inkl.
      des kontraintuitiven Ergebnisses, dass das *schwächer* trainierte Modell
      mit schema-beschränktem Decoding beide "sauberen" Trainingslösungen
      schlägt, und warum das bewusst nur lokal läuft, nicht im
      Azure-Deployment (Kostenrechnung dort).
- [x] **Narrator** — eine Zeile Flavor-Text für Event-, Rast- und
      Shop-Räume (`agent/narrator.py`). Bewusst kein voller Agent: kein
      Budget zu schützen, also kein Schema und kein Retry; die Zahlen hängt
      immer die Spiellogik an. `prefetch.py` erzeugt Gegner und Flavor-Text
      für erreichbare Räume schon im Hintergrund, solange man auf die Karte
      schaut.
- [ ] **Difficulty-Agent** — passt zukünftige Encounter-Budgets an den
      Run-Verlauf an.
- [ ] **Politur** — Tests, die sicherstellen, dass agenten-generierter
      Content immer im Balance-Budget bleibt; weitere Content-Typen
      (Relikte, Events) für den Encounter-Agent; echte Kartenvielfalt fürs
      Kampfdeck statt des aktuellen Platzhalter-Startdecks.

## Projektstruktur

```
src/agentic_rogue_like/
├── models.py       Pydantic-Datenmodelle (RunState, PlayerState, MapNode, Enemy, Card, ...)
├── map_gen.py      Prozedurale Etagen-/Node-Map
├── combat.py       Kartenbasierter Kampf: Deck/Hand/Feld, Zieh-/Ablagelogik
├── cards.py        Startdeck mit IT-Namen (Exploit, Firewall, Hotfix, ...; Aktions- + permanente Karten)
├── events.py       Event-/Rest-/Shop-Auflösung
├── enemies.py      Statischer Gegner-Pool (Fallback für den Encounter-Agent)
├── engine.py       Der deterministische Kern-Loop, den CLI und API beide treiben
├── agent/          LangGraph-Encounter-Agent, Tool-Schema, Etagen-Budgets, Narrator, Ollama-Anbindung
├── prefetch.py     Erzeugt LLM-Inhalte erreichbarer Räume im Hintergrund
├── balance_sim.py  Bot-Simulation für das Balancing (uv run balance-sim)
├── cli.py          Terminal-Frontend (input()/print()-Loop)
├── api.py          FastAPI-HTTP-Frontend fürs Web-UI (uvicorn agentic_rogue_like.api:app)
└── sessions.py      Hält Run-Zustand zwischen HTTP-Requests am Leben

frontend/           React + Vite + TypeScript — Intro, Dungeon-Map, Kampf-Arena, Event-Prompts
                    (Kampfeffekte in frontend/src/fx/)
balance/            Beispiel-Varianten (JSON) für den Balancing-Simulator
tests/              pytest-Suite (Engine, Kampf, API, Encounter-Agent/-Schema)
training/           Eigenes uv-Projekt: Fine-Tuning-Pipeline für den Encounter-Agent
                    (Datengenerierung, Colab-Notebook, Eval-Harness, GGUF/Ollama-Serving,
                    siehe training/README.md und training/RESULTS.md)
```

## Warum so gebaut

Die meisten Roguelikes beziehen ihre Abwechslung aus großen, handgeschriebenen
Content-Tabellen. Hier ist es umgekehrt: Der Content-Generator ist ein Agent,
der zustandsbewusste Entscheidungen (was spawnt, wie stark, was es tut) über
ein striktes Schema trifft — statt entweder einer statischen Tabelle oder
unbeschränktem Freitext. Der deterministische Kern-Loop wurde zuerst gebaut
und getestet, komplett ohne LLM, damit das Spiel für sich spielbar und seine
Balance nachvollziehbar ist, bevor ein Agent anfängt, Content hineinzugenerieren.

## Stack

Python, Pydantic (State + Tool-Schemas), LangGraph + Groq (Agent), FastAPI +
Uvicorn (Web-API), React + Vite + TypeScript (Frontend), pytest, ruff,
Docker, Azure Container Apps + Static Web Apps (Deployment). Optional statt
Groq: ein selbst per LoRA/QLoRA fein-getuntes Qwen2.5-1.5B, quantisiert
(GGUF) und lokal über Ollama serviert — siehe `training/`.

## Entwicklung

### Terminal

```bash
uv sync
uv run pytest
uv run ruff check .
uv run agentic-rogue-like
```

Für den Encounter-Agent wird ein `GROQ_API_KEY` benötigt (z. B. in einer
lokalen, nicht eingecheckten `.env`-Datei). Er ist standardmäßig aus — nur
mit zusätzlich gesetztem `ENCOUNTER_AGENT_ENABLED=1` generiert die Engine
Gegner live über Groq statt aus dem statischen Pool. `pytest` lädt keine
`.env` und setzt das Flag nie, damit die Test-Suite schnell und ohne
Netzwerk bleibt.

Statt Groq lässt sich auch ein selbst fein-getuntes, lokal per
[Ollama](https://ollama.com) serviertes Modell nutzen:
`ENCOUNTER_AGENT_MODEL_SOURCE=ollama` (Standard: `groq`), optional
`ENCOUNTER_AGENT_OLLAMA_MODEL=<tag>` für einen bestimmten Ollama-Modell-Tag.
Braucht einen lokal laufenden Ollama-Server auf demselben Rechner — Details,
Trainings-Pipeline und volle Auswertung gegen die Groq-Baseline in
[`training/README.md`](training/README.md) und
[`training/RESULTS.md`](training/RESULTS.md).

### Web (API + Frontend)

```bash
uv run agentic-rogue-like-api   # FastAPI auf http://localhost:8000
```

```bash
cd frontend
npm install
npm run dev                     # Vite-Dev-Server, meist http://localhost:5173
```

Die API erlaubt standardmäßig nur `http://localhost:5173` per CORS
(`FRONTEND_ORIGINS`-Env-Var, kommagetrennt — so läuft dasselbe Image lokal
und in Produktion ohne Rebuild). Das Frontend liest seinerseits die
API-Adresse aus `VITE_API_BASE_URL` zur Build-Zeit.

## Balancing testen

`uv run balance-sim` spielt mit einem Bot tausende Kämpfe und komplette Runs
durch (ohne LLM, Gegner zufällig innerhalb der Budgets aus
`agent/budgets.py`) und zeigt pro Gegnerstufe Siegquote, Züge pro Kampf und
verlorene HP, dazu die Run-Siegquote und auf welcher Etage Runs enden.

Für neue Karten oder Anpassungen eine Variante als JSON anlegen (nur was sich
ändert, Beispiele in `balance/`) und neben die aktuellen Werte stellen:

```bash
uv run balance-sim --compare balance/gegner-staerker.json
uv run balance-sim --compare balance/beispiel-neue-karte.json --bot naive
```

Aktueller Stand (Smart-Bot, 2000 Runs): Spieler 60 HP / Angriff 3, Exploit
macht 5 (+3), nach jedem gewonnenen Kampf kommt eine Karte ins Deck. Die
Kurve steigt gleichmäßig an, der Boss ist der Höhepunkt:

| Stufe | Züge | HP-Verlust im Run | Sieg im Run |
| --- | --- | --- | --- |
| early | 2.8 | 8 | 99 % |
| mid | 3.7 | 14 | 87 % |
| elite | 4.8 | 23 | 80 % |
| boss | 4.9 | 29 | 36 % |

Run-Siegquote: 27 % (Smart-Bot), 34 % (Naive-Bot), 13 % ohne
Kartenbelohnungen (`--no-rewards`) — das Deck-Building trägt also spürbar.
Die Bots wählen Belohnungen stur nach Seltenheit bzw. zufällig; wer gezielt
auf eine Strategie baut, sollte deutlich öfter gewinnen.

## Karten

Nach jedem gewonnenen Kampf (außer dem Boss) gibt es drei Karten zur Auswahl
(oder Überspringen), gewichtet nach Seltenheit — nach Elite-Kämpfen sind
seltene wahrscheinlicher. Der Pool (`cards.py`) ist um drei Strategien gebaut:

- **Permanente** — Botnet, Load Balancer, Daemon, Mainframe werden stärker,
  je voller das Feld ist; Kernel Panic kassiert das Feld am Ende ein.
- **Friedhof** — Brute Force, Fork Bomb, Honeypot und Memory Dump werfen
  Karten ab (Kosten!), Stack Overflow skaliert damit, Rollback holt zurück.
- **Einmal-Karten** (1×) — Zero-Day, Sandbox, Backup sind stark, werden aber
  für den Rest des Kampfes verbannt; Payload wächst mit dem Verbannt-Stapel,
  Undelete holt eine verbannte Karte zurück.

Karten, die mitten im Zug Karten auf die Hand bringen (ziehen, zurückholen),
sind absichtlich alle Einmal-Karten: Ohne Energie-System wären sonst
Endlos-Kombos möglich.

## Deployment

Jeder Push auf `master` löst `.github/workflows/deploy.yml` aus: baut das
Backend-Image (`Dockerfile`, `uv`) direkt in der Azure Container Registry,
aktualisiert die Azure Container App darauf, baut danach das Frontend gegen
die frisch deployte API-URL und published es nach Azure Static Web Apps.
Login läuft über OIDC/Federated Credentials — kein Passwort oder
Registry-Secret im Repo. Zwei Deploys laufen nie gleichzeitig
(`concurrency`): ein neuer Push wartet, bis der laufende fertig ist. Es gibt aktuell kein separates CI-Test-Gate vor dem
Deploy; `pytest` läuft nur manuell/lokal.
