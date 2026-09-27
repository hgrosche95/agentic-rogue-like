# Frontend

React + Vite + TypeScript. Spielt einen Run im Browser über die FastAPI-Schicht
(`src/agentic_rogue_like/api.py`); Start und Umgebungsvariablen stehen in der
[Haupt-README](../README.md#web-api--frontend).

- `components/IntroScreen.tsx` – Story-Intro beim ersten Besuch (in `localStorage` gemerkt, überspringbar)
- `components/SettingPicker.tsx` – Wahl des Settings für den Encounter-Agenten
- `components/DungeonMap.tsx` – klickbare Node-Map
- `components/CombatPanel.tsx`, `CombatArena.tsx` – Kampf mit 5-Slot-Feld, Hand und Arena aus Blender-Ebenen (WebP)
- `components/EnemyMonster.tsx` – zeichnet jeden generierten Gegner als SVG aus Name, HP, Angriff und Setting
- `hackerCommands.ts` – die Befehle, die Dr. Chronos pro Karte ins Terminal tippt
- `cardFlight.ts` – Flug einer Karte von der Hand aufs Feld

```bash
npm install
npm run dev     # http://localhost:5173, erwartet die API auf http://localhost:8000
npm run build
npm run lint
```
