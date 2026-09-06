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

## Status

- [x] **Skelett** — Projekt-Setup, Kern-Datenmodelle (`RunState`,
      `PlayerState`, `MapNode`, `Enemy`)
- [x] **Deterministischer Kern-Loop** — prozedural generierte Node-Map,
      würfelbasierter Kampf, Event-/Rest-/Shop-Auflösung,
      Sieg-/Niederlage-Bedingungen. Vollständig spielbar im Terminal, noch
      ohne LLM.
- [ ] **Encounter-Agent** — ein LangGraph-Agent, der Gegner über constrained
      Tool-Calls generiert und gegen ein Etagen-Budget validiert, mit
      Retry-Schleife bei Budget-Verstoß. Für Gegner voll eingeklinkt: die
      Engine ruft ihn über `ENCOUNTER_AGENT_ENABLED=1` live an und fällt bei
      jedem Fehler (API nicht erreichbar, Budget nach 3 Versuchen nie
      getroffen, ...) auf den statischen Pool zurück — in einem echten Lauf
      bereits beobachtet und mit `monkeypatch` deterministisch getestet.
      Relikte und Events als weitere Content-Typen fehlen noch.
- [ ] **Narrator-Agent** — verpackt generierte/mechanische Ergebnisse in
      Flavor-Text.
- [ ] **Difficulty-Agent** — passt zukünftige Encounter-Budgets an den
      Run-Verlauf an.
- [ ] **Politur** — schönere Terminal-Oberfläche, ein aufgezeichneter Run,
      Tests, die sicherstellen, dass agenten-generierter Content immer im
      Balance-Budget bleibt.

## Warum so gebaut

Die meisten Roguelikes beziehen ihre Abwechslung aus großen, handgeschriebenen
Content-Tabellen. Hier ist es umgekehrt: Der Content-Generator ist ein Agent,
der zustandsbewusste Entscheidungen (was spawnt, wie stark, was es tut) über
ein striktes Schema trifft — statt entweder einer statischen Tabelle oder
unbeschränktem Freitext. Der deterministische Kern-Loop wurde zuerst gebaut
und getestet, komplett ohne LLM, damit das Spiel für sich spielbar und seine
Balance nachvollziehbar ist, bevor ein Agent anfängt, Content hineinzugenerieren.

## Stack

Python, Pydantic (State + Tool-Schemas), LangGraph + Groq (Agent), pytest, ruff.

## Entwicklung

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
