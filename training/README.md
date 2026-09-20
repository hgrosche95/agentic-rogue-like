# training/

Fine-Tuning- und Eval-Pipeline für den Encounter-Agent aus
[`../src/agentic_rogue_like/agent/`](../src/agentic_rogue_like/agent/): ersetzt
den Groq-Call (`_model()` in `encounter_agent.py`) durch ein kleines,
selbst fein-getuntes Open-Weight-Modell — mit Zahlen belegt, nicht mit
Eindruck.

## Warum ein eigenes uv-Projekt statt Teil des Hauptpackages

Eigener Lebenszyklus: Notebooks, generierte Datensätze und (später) große
Modell-Gewichte gehören nicht ins Docker-Image der laufenden App und sollen
`uv.lock`/`pyproject.toml` des Hauptprojekts nicht mit schweren,
trainingsspezifischen Abhängigkeiten (torch, peft, trl, ...) verschmutzen.
`training/` ist deshalb ein eigenständiges uv-Projekt mit eigenem `.venv` und
eigenem Lockfile, das den Hauptpackage per Pfad-Abhängigkeit einbindet
(`tool.uv.sources` in `pyproject.toml`) — so werden `EnemyProposal`,
`EnemyBudget`, `validate_proposal` und `budget_for` aus dem Hauptpackage
wiederverwendet statt dupliziert; die Budget-Validierung, die zur Laufzeit
als Guard dient, ist hier zugleich die Datenqualitätskontrolle für
generierte Trainingsdaten.

```bash
cd training
uv sync
```

Braucht denselben `GROQ_API_KEY` wie das Hauptprojekt (aus `../.env`).

## Struktur

```
training/
├── data_gen/    Phase 1 — synthetische Trainingsdaten (Kontext -> EnemyProposal), gefiltert durch validate_proposal
├── eval/        Phase 4 — Harness: Groq-Baseline vs. fein-getuntes Modell (Gültigkeit, Budget, Diversität, Kosten/Latenz)
├── notebook/    Phase 3 — Colab-Notebook fürs LoRA/QLoRA-Fine-Tuning (Colab Free-Tier T4, kein lokales GPU-Training)
├── serving/     Phase 5 — GGUF-Export + Ollama + dünner FastAPI-Wrapper mit derselben Schnittstelle wie _model()
└── artifacts/   Gitignored — heruntergeladene/quantisierte Modell-Gewichte, generierte Datensätze
```

## Status

- [x] Eval-Harness + Groq-Baseline (zuerst gebaut, bevor es überhaupt ein
      eigenes Modell gibt — liefert die Vergleichszahlen und validiert den
      Harness gegen ein bekanntes Verhalten). Ergebnis:
      `artifacts/eval_reports/groq-baseline.md`.
- [x] Trainingsdaten-Generierung — 296 Beispiele (217 train / 40 val / 39
      test), alle 4 Budget-Tiers abgedeckt. Ergebnis:
      `artifacts/dataset/data_card.md`.
- [x] Basismodell-Entscheidung — Qwen2.5-1.5B-Instruct, siehe
      [`MODEL_CHOICE.md`](MODEL_CHOICE.md).
- [ ] Fine-Tuning (Colab, LoRA/QLoRA) — Notebook
      [`notebook/finetune_qwen.ipynb`](notebook/finetune_qwen.ipynb) geschrieben
      (Rang 16, Alpha 32, Dropout 0,05, q/k/v/o_proj, 3 Epochen + Early
      Stopping), **noch nicht in Colab ausgeführt/verifiziert**.
- [ ] Eval-Harness gegen das fein-getunte Modell
- [ ] Quantisierung + Ollama-Serving
- [ ] Integration in `encounter_agent.py` hinter konfigurierbarem Switch
- [ ] Ergebnisse im Haupt-README dokumentieren
