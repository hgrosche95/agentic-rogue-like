# Basismodell-Entscheidung

**Gewählt: Qwen2.5-1.5B-Instruct** (Apache 2.0)

## Kandidaten

| | Qwen2.5-1.5B-Instruct | Llama-3.2-3B-Instruct | Phi-3-mini (3.8B) |
|---|---|---|---|
| Lizenz | Apache 2.0 (voll frei) | Meta Llama Community License (Nutzungsauflagen) | MIT (voll frei) |
| Parameter | 1.5B | 3B | 3.8B |
| JSON/strukturierte Ausgabe | Explizit als Stärke dokumentiert | Gut für Tool-Routing, JSON-Qualität nicht explizit belegt | Explizit dokumentierte Verbesserung (Score 1.9→60.1, Juni-2024-Update) |
| Kontextfenster | 128K | ausreichend für unsere ~300-Token-Prompts | 4K Standard (128K-Variante verfügbar) |
| GGUF/Ollama-Support | Exzellent | Exzellent | Gut, offiziell dokumentiert |

Quellen: [Qwen2.5 Blog](https://qwenlm.github.io/blog/qwen2.5/), [Qwen2.5-3B-Instruct — Hugging Face](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct), [Llama 3.2 Ollama Cheat Sheet](https://computingforgeeks.com/ollama-models-cheat-sheet/), [Phi-3-Mini-4K-Instruct — Hugging Face](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct) (Stand: 2026-09-20)

## Begründung

Das kleinste Modell im Vergleich ist hier die begründete Wahl, nicht nur die billigste:

1. **Die Aufgabe ist eng umrissen.** Aus einem ~300-Token-Prompt (Setting + Budget) ein 5-Feld-JSON
   erzeugen braucht keine 3-4 Milliarden Parameter allgemeine Fähigkeiten - die blieben ungenutzt und
   kosten nur Trainingszeit und CPU-Latenz beim Serving.
2. **Kleinstes Modell = schnellste CPU-Inferenz.** Trifft direkt das Erfolgskriterium "deutlich
   schneller" aus dem Projektauftrag.
3. **Apache 2.0 ist die sauberste Lizenz im Vergleich.** Qwens eigene 3B-Variante steht unter der
   restriktiveren "Qwen License" - nur die kleineren Varianten (inkl. 1.5B) sind Apache 2.0.
4. **JSON-Stärke ist explizit dokumentiert**, passt direkt zum Schema (`EnemyProposal`).
5. **Weniger Overfitting-Risiko** bei nur 217 Trainingsbeispielen als ein größeres Modell.

### Warum nicht "mehr Kapazität für mehr Kreativität"

Naheliegender Einwand: ein größeres Modell könnte kreativere Gegner-Beschreibungen liefern. Zwei
Gegenargumente, warum das hier nicht zieht:

- **Diversität kommt bei dieser Aufgabe primär aus Sampling-Temperatur und der Diversität der
  Trainingsdaten, nicht aus Modellgröße.** Selbst Groqs 20B-Modell (Baseline) zeigte bei Boss-Gegnern
  zeitweise eine Attack-Streuung von 0 (siehe `eval/artifacts/eval_reports/groq-baseline.md`) - Größe
  ist kein Kreativitäts-Garant.
- **Der Auftrag schließt ein Hyperparameter-Sweep explizit aus** ("bewusste, begründete
  Einzelentscheidungen reichen" statt automatisches Tuning). Ein größeres Modell hat mehr
  Freiheitsgrade (Lernrate, Trainingsdauer, Overfitting-Verhalten), bei denen die eine gewählte
  Konfiguration ohne Nachjustieren eher daneben liegen kann, und längere Trainingszeit pro Epoche -
  also weniger Spielraum für einen zweiten Versuch innerhalb eines Colab-Sessions-Limits. Ein
  kleineres Modell ist nachsichtiger gegenüber einer einzelnen, nicht nachjustierten Entscheidung.

Phi-3-mini (MIT-Lizenz, ebenfalls starke JSON-Fähigkeit) wäre die valide Alternative gewesen, aber
ohne erkennbaren Vorteil für diese enge Aufgabe - nur größer und langsamer.
