# Trailer

Erzeugt `docs/trailer.mp4` aus echtem Gameplay: Aufnahme im Headless-Chromium,
prozeduraler Soundtrack, Schnitt mit Texteinblendungen.

1. Backend (`uv run uvicorn agentic_rogue_like.api:app`) und Frontend (`npm run dev`) starten.
2. `node record2.mjs recA Cyberpunk 7500` und `node record2.mjs recB "Haunted Carnival" 7500 skip`
   (Playwright). `timectl.js` ersetzt die Uhr der Seite, jedes Bild rückt sie um 1/30 s vor –
   so wird die Aufnahme flüssig, egal wie langsam der Headless-Browser rendert.
3. `python3 music.py score.wav` – Soundtrack (numpy/scipy, 120 BPM, A-Moll).
4. `python3 compose.py timeline.py trailer.mp4` – schneidet die Shots aus `timeline.py`,
   legt Texte, Glitches, Flashes und den Soundtrack darüber (Pillow, imageio-ffmpeg,
   Fonts Orbitron/JetBrains Mono in `fonts/`).
