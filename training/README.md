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
- [x] Fine-Tuning (Colab, LoRA/QLoRA) — drei Läufe, alle über dasselbe
      [`notebook/finetune_qwen.ipynb`](notebook/finetune_qwen.ipynb) (die
      Datei zeigt Lauf 3; die Konfigurationen von Lauf 1 und 2 sind in
      `RESULTS.md` dokumentiert). Modelle liegen in `artifacts/model/merged*/`
      bzw. `adapter*/`.
- [x] Eval-Harness gegen das fein-getunte Modell — **volles Ergebnis in
      [`RESULTS.md`](RESULTS.md)**, alle drei Läufe mit identischen Parametern
      gegen die vollständige Groq-Baseline (310 Calls) gemessen. Kurz: Lauf 2
      und 3 lernen das Schema zuverlässig ein, verlieren dabei aber massiv
      Antwortvielfalt; Lauf 3 zeigt, dass das an der LoRA-Kapazität liegt und
      nicht an der Trainingsdauer. Am besten schneidet ausgerechnet Lauf 1 mit
      schema-beschränktem Decoding ab — schemakonform per Konstruktion und
      vielfältiger als Groq selbst. Das ist deshalb die Voreinstellung.
- [x] Quantisierung + Ollama-Serving — bf16-Modell per `llama.cpp` nach GGUF
      konvertiert und auf Q4_K_M quantisiert (2,94GB → 935MB), als
      `qwen2.5-enemy-generator` in Ollama importiert
      ([`serving/Modelfile`](serving/Modelfile)).
      [`../src/agentic_rogue_like/agent/ollama_model.py`](../src/agentic_rogue_like/agent/ollama_model.py)
      ist ein `encounter_agent._model()`-kompatibler Wrapper
      (`with_structured_output(...).invoke(...)`), bewusst **ohne** Ollamas
      Tool-Calling — das Modell wurde auf rohen JSON-Text trainiert, nicht auf
      ein Tool-Call-Format. Lebt im Hauptpackage, nicht hier, weil er zur
      Laufzeit im Spiel läuft (siehe Schritt "Integration"). Läuft
      nachweislich durch den echten Produktions-Graphen. Erster Befund (Lauf 1): das Modell lässt
      gelegentlich `attack_name` weg — vollständig ausgewertet in
      [`RESULTS.md`](RESULTS.md).
- [x] Integration in `encounter_agent.py` hinter konfigurierbarem Switch —
      `ENCOUNTER_AGENT_MODEL_SOURCE=ollama` (Standard: `groq`),
      `ENCOUNTER_AGENT_OLLAMA_MODEL` überschreibt den Modell-Tag. Bestehender
      Fallback auf den statischen Pool unverändert — deckt Ollama-Ausfälle
      automatisch mit ab. Live gegen den echten `enemy_for_node()`-Pfad und
      den laufenden Ollama-Server verifiziert.
- [x] Ergebnisse im Haupt-README dokumentiert — siehe dort Status
      "Encounter-Agent-Destillation" und den Abschnitt "Entwicklung".
