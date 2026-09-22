# Ergebnisse: Groq gpt-oss-20b vs. fein-getuntes Qwen2.5-1.5B

**Stand: Zwischenstand (2026-09-22)** - nach Lauf 1 des Fine-Tunings. Die Groq-Baseline ist jetzt
vollständig (alle 4 Tiers, 310 Calls). Offen ist Lauf 2 des Fine-Tunings (Colab-GPU-Kontingent war
erschöpft, siehe "Bekannte Lücken"). Alle Zahlen stammen aus `artifacts/eval_reports/*.md` und sind
mit `uv run python -m eval.run_eval ...` reproduzierbar (die Berichte selbst sind gitignored).

## Kurzfassung

- **Ohne Zusatz ist das Fine-Tune nicht gut genug:** nur **23-36 %** gültige Antworten (Groq: ~99 %,
  unverändertes Basismodell: 0 %). Fast immer fehlt das letzte JSON-Feld `attack_name`.
- **Mit schema-beschränktem Decoding** (siehe unten) sind **604 von 604** Antworten gültig und im Budget,
  auch auf Settings, die das Modell nie gesehen hat.
- **Latenz ist der Preis:** ~3,7 s statt ~1,1 s (auf einer normalen CPU, ohne GPU), also gut dreimal langsamer.
- **Kosten:** $0 statt ~$0,14 pro 1000 Aufrufe. Absolut winzig - der eigentliche Gewinn ist die Unabhängigkeit
  von API-Key, Netz und Tageslimit (Groqs 200k-Tokens/Tag-Limit hat die Entwicklung mehrfach ausgebremst).

## Vergleich

| | Groq gpt-oss-20b | Fine-Tune Q4, ohne Beschränkung | Fine-Tune Q4, **mit** Beschränkung |
|---|---|---|---|
| Gültige Antworten (Schema) | **98,7 %** (n=310, alle 4 Tiers) | 22,7 % gesehen / 35,9 % ungesehen (n=300/304) | **100 % / 100 %** (n=300/304) |
| Im Budget, wenn gültig (1. Versuch) | 100 % | 100 % | 100 % |
| Eindeutige Namen je Tier | 0,75 / 0,73 / 0,82 / 0,88 | ~1,0 | 0,97-1,0 |
| Eindeutige Angriffsnamen je Tier | 0,93 / 1,00 / 0,92 / 0,96 | ~1,0 | 0,75-0,91 |
| Latenz p50 / p95 | **1,09 / 1,78 s** | 3,6 / 3,9 s | 3,6-3,7 / 3,9-4,1 s |
| Kosten / 1000 Aufrufe | **$0,15** (gemessene Tokens x Listenpreis) | $0 (lokal) | $0 (lokal) |

Tier-Reihenfolge überall early/mid/elite/boss. Groq-N pro Tier: 118/42/75/75.

"Gesehen" = die fünf `SETTING_PRESETS`, die alle im Trainings-Split liegen (das Modell kennt diese Prompts
wörtlich). "Ungesehen" = `candy kingdom`, `swamp witch coven` (Test-Split, nie trainiert). Der Vergleich mit Groq
ist auf "gesehen" fair, "ungesehen" ist der ehrliche Generalisierungswert. Es gibt keine Lücke dazwischen.

## Was schiefging, und wie wir es eingegrenzt haben

232 der 300 Fehlschläge (gesehene Prompts) sind syntaktisch **gültiges JSON, dem ein Feld fehlt** - in 218 Fällen
`attack_name`; nur 12 sind echte Syntaxfehler. Ausgeschlossen wurde:

| Verdacht | Test | Ergebnis |
|---|---|---|
| Quantisierung (Q4_K_M) | dasselbe Modell als unquantisiertes f16 (n=80) | 28,8 % - kein Unterschied |
| Prompt-Template | `ollama show --template` gegen das Trainings-Template | identisch (Qwen-Standard inkl. System-Prompt) |
| Fehler in den Trainingsdaten | alle 217 Ziele geprüft | alle enthalten `attack_name`, gleiche Feldreihenfolge |
| Auswendiglernen | ungesehene Settings | *besser* als gesehene (35,9 % vs. 22,7 %) |
| Zu hohe Temperatur | Temperatur 0.2 statt 0.9 (n=80) | *schlechter* (10 %) |
| Fine-Tuning hat nichts gebracht | unverändertes Qwen2.5-1.5B-Instruct (n=80) | 0 % - das Fine-Tune hat also gewirkt, nur nicht genug |

Übrig bleibt ein Trainingsproblem. Die `trl`-Quelle (Version 1.13.0) bestätigt, dass der Loss bei unserem
Textfeld-Datensatz über die **gesamte Sequenz** gerechnet wurde, inklusive des fast konstanten Prompts (gemessen
142 Prompt- und 55 Antwort-Tokens, also rund 70 % Prompt); nur bei Prompt/Completion-Daten wird automatisch nur
die Antwort gewertet. Dazu kamen nur 42
Trainingsschritte, und der Val-Loss sank bis zuletzt (Early Stopping griff nie): das Modell war unterangepasst.
Warum es gerade das *letzte* Feld trifft, wissen wir nicht sicher.

## Schema-beschränktes Decoding

Ollamas `format`-Parameter (`serving/ollama_model.py`, Flag `--constrained` im Eval) übersetzt das
`EnemyProposal`-Schema in eine Grammatik. Bei jedem Token sind nur noch Fortsetzungen erlaubt, die zum Schema
passen; ein Objekt ohne `attack_name` kann nicht mehr geschlossen werden. Dasselbe Modell, derselbe Prompt, keine
Zusatzlatenz (3,6 s mit und ohne). **Es bringt dem Modell nichts bei** und prüft das Budget nicht - dass alle 604
Antworten im Budget lagen, ist eine echte Leistung des Fine-Tunes.

**Wichtige Einschränkung:** Groq erzwingt das Schema *nicht* hart - es übergibt es als Tool-Definition, und wir
haben bei der Datengenerierung selbst `tool_use_failed`-Fehler gesehen (~1-2 %). Der Vergleich "100 % gegen
~99 %" ist deshalb kein reiner Qualitätsgewinn, sondern teilweise ein Konstruktionseffekt: strukturelle Gültigkeit
ist mit Beschränkung garantiert. Belastbar gemessen sind Budget-Treue, Diversität und Latenz.

## Trainingsentscheidungen (Lauf 1)

- **Daten:** 300 Kandidaten von Groq `gpt-oss-20b` erzeugt, 296 (98,7 %) durch `validate_proposal` akzeptiert.
  Split **217 / 40 / 39** (train/val/test) auf **Setting-Ebene**, damit kein (Tier, Setting)-Paar über die Grenze
  wandert und Beinahe-Duplikate den Val-Wert schönen. 15 Settings: 5 Presets + 10 selbst gewählte Freitext-Settings.
- **Modell:** Qwen2.5-1.5B-Instruct (Apache 2.0), Begründung in `MODEL_CHOICE.md`.
- **QLoRA statt Vollständigem Fine-Tuning:** volles Fine-Tuning von 1,5 Mrd. Parametern braucht mit AdamW
  grob 18 GB (Gewichte + Gradienten + Optimizer-Zustände, vor den Aktivierungen); Colabs T4 hat 16 GB.
  LoRA trainiert ~4,4 Mio. Parameter (0,28 %), das eingefrorene Basismodell liegt in 4-Bit (NF4).
- **Hyperparameter:** Rang 16, Alpha 32 (Faustregel 2x Rang), Dropout 0,05, nur Attention-Schichten
  (Regularisierung bei 217 Beispielen), Lernrate 2e-4 mit Cosine-Schedule, effektive Batchgröße 16,
  3 Epochen mit Early Stopping (Geduld 1) auf dem Val-Loss. Ein einzelner begründeter Wurf, kein Sweep.
- **Verlauf:** Train-Loss 2,12 → 0,66 → 0,51, Val-Loss 1,26 → 0,57 → 0,54, 12,3 Minuten auf der T4.
- **Merge:** aus dem 4-Bit-Trainingsmodell direkt gemergt blieb das Ergebnis intern 4-Bit (Dateigröße 1,6 statt
  ~3 GB, `quantization_config` in der `config.json`). Behoben, indem das Basismodell frisch in bf16 geladen und der
  Adapter darauf gemergt wird (3,09 GB).
- **Quantisierung:** GGUF f16 (2,94 GB) → Q4_K_M (935 MB), in Ollama als `qwen2.5-enemy-generator`.

## Lauf 2 (vorbereitet, noch nicht gelaufen)

Aus den Befunden abgeleitet, kein Sweep: Loss nur auf der Antwort (Prompt/Completion-Format), 5 Epochen mit
Early-Stopping-Geduld 2, LoRA auf allen linearen Schichten (18,5 Mio. Parameter, 1,2 %), Prompt unverändert. Das
Notebook `notebook/finetune_qwen.ipynb` enthält einen Schnelltest (Gültigkeit auf den 40 Val-Prompts) vor dem
Download. Die kostenlose Colab-GPU war zum Zeitpunkt dieses Stands gesperrt.

## Bekannte Lücken und Vorbehalte

- **Fine-Tune Lauf 2 steht noch aus** - Colabs kostenlose GPU war zum Zeitpunkt dieses Stands gesperrt
  (Tageskontingent). Sobald verfügbar: Notebook laufen lassen, Schnelltest-Ergebnis prüfen, bei Erfolg
  neu quantisieren/importieren und die Eval-Läufe (`finetuned-seen`/`finetuned-heldout`, mit und ohne
  `--constrained`) gegen `qwen2.5-enemy-generator-v2` wiederholen.
- **Kosten** gemessen aus Tokenzahlen (320,6 ein / 427,8 aus pro Aufruf, gemittelt über alle 4 Tiers) mal
  Groq-Listenpreis vom 2026-09-17; Hardware und Strom des lokalen Modells sind nicht eingerechnet.
- **Latenz** sequenziell, eine Anfrage nach der anderen, Groq über das Netz, Ollama auf deiner CPU.
- **Stichprobengröße:** bei n~300 liegt die Unsicherheit einer Rate um 50 % bei etwa ±3 Prozentpunkten, bei den
  n=80-Diagnoseläufen bei ±5. Die Groq-Tiers early (118) und mid (42) sind unterschiedlich groß, weil sie aus
  zwei zusammengeführten Läufen stammen (ein Überschreibungs-Bug im Eval-Harness kostete einen Teil des
  ersten mid-Laufs, seither behoben, siehe `eval/report.py`).
- **Diversität:** Elite-Gegner des Fine-Tunes haben in beiden Läufen **immer denselben Angriffswert**
  (Streuung 0,0), eine echte Schwäche. Bei Groq zeigte sich in einer frühen, kleinen Stichprobe (n=25)
  dasselbe Muster bei Boss-Gegnern - mit der jetzigen vollen Stichprobe (n=75) liegt die Streuung dort bei
  0,80, war also ein Artefakt der kleinen Stichprobe, kein echter Befund. Die Elite-Beobachtung beim
  Fine-Tune ist mit n=75 (gesehen) bzw. n=76 (ungesehen) bereits groß genug, um kein reines Stichprobenrauschen
  zu sein.
