# Ergebnisse: Groq gpt-oss-20b vs. fein-getuntes Qwen2.5-1.5B

**Stand: 2026-09-23, nach drei Fine-Tuning-Läufen.** Groq-Baseline vollständig (alle 4 Tiers, 310 Calls),
alle drei Läufe mit identischen Parametern gegen sie gemessen. Alle Zahlen stammen aus
`artifacts/eval_reports/*.md` und sind mit `uv run python -m eval.run_eval ...` reproduzierbar (die
Berichte selbst sind gitignored).

## Kurzfassung

- **Lauf 1** (Attention-only-LoRA) war für sich unbrauchbar: nur 23-36 % schemakonforme Antworten, fast
  immer fehlte `attack_name`. Mit schema-beschränktem Decoding wurde daraus 100 % - damals als "Krücke"
  eingeordnet.
- **Lauf 2** (LoRA auf allen linearen Schichten, Loss nur auf der Antwort, 5 Epochen) behob die Ursache
  im Training: 100 % gültig ganz ohne Beschränkung. Handelte sich dafür aber einen **Einbruch der
  Antwortvielfalt** ein.
- **Lauf 3** sollte klären, ob der Einbruch an der Kapazität oder der Trainingsdauer lag, und hielt alles
  aus Lauf 2 bis auf die Epochen (3 statt 5). Antwort: **an der Dauer lag es nicht.** Die Diversität blieb
  gleich schlecht, und die Gültigkeit fiel sogar leicht (96,7 % / 99,3 %).
- **Das überraschende Ergebnis:** Über alle Achsen gewinnt ausgerechnet die vermeintliche Krücke.
  **Lauf 1 + Beschränkung** ist schemakonform per Konstruktion und hat **0,95 eindeutige Namen** - mehr
  als Groq selbst (0,67) und doppelt so viel wie Lauf 2/3 (0,45-0,56). Es ist deshalb die Voreinstellung
  in `ollama_model.py`.
- **Latenz** bleibt der Preis: ~3,6 s statt Groqs ~1,1 s (normale CPU, ohne GPU), etwa dreimal langsamer.
- **Kosten:** $0 statt ~$0,15 pro 1000 Aufrufe. Absolut winzig - der eigentliche Gewinn ist die
  Unabhängigkeit von API-Key, Netz und Tageslimit (Groqs 200k-Tokens/Tag-Limit hat die Entwicklung diese
  Woche mehrfach ausgebremst).

## Vergleich

Werte als "gesehen / ungesehen", wo getrennt gemessen. Alle Fine-Tune-Zahlen aus je 300 (gesehen) bzw.
304 (ungesehen) Aufrufen, Groq aus 310.

| | Groq | Lauf 1 ohne Beschr. | **Lauf 1 + Beschr.** | Lauf 2 (5 Ep) | Lauf 3 (3 Ep) |
|---|---|---|---|---|---|
| Gültige Antworten | 98,7 % | 22,7 / 35,9 % | **100 / 100 %** | 100 / 100 % | 96,7 / 99,3 % |
| Im Budget, wenn gültig | 100 % | 100 % | **100 %** | 100 % | 100 % |
| Eindeutige Namen | 0,67 | ~1,0 (der validen) | **0,95 / 0,94** | 0,45 / 0,56 | 0,56 / 0,52 |
| Anteil häufigster Name | 12,7 % | - | **1,0 %** | 12,7 / 6,6 % | 6,2 / 13,2 % |
| Verschiedene HP-Werte je Tier | 5/4/7/7 | - | **4/4/9/7** | 1/3/6/2 | 1/3/6/2 |
| Latenz p50 | **1,09 s** | 3,6 s | 3,6 s | 3,5 s | 3,6 s |
| Kosten / 1000 Aufrufe | $0,15 | $0 | **$0** | $0 | $0 |

Zur Lesart der Diversitätsmaße: Die **Unique-Quote** sinkt mechanisch mit wachsender Stichprobe und taugt
nur für gleich große Stichproben (hier gegeben). Der **Anteil des häufigsten Namens** ist robuster. Die
**Anzahl verschiedener HP-Werte je Tier** (Reihenfolge early/mid/elite/boss) ist aussagekräftiger als eine
Standardabweichung über alle Tiers hinweg, weil jedes Tier eine andere Budget-Spanne hat (16/21/26/41
mögliche Werte).

"Gesehen" = die fünf `SETTING_PRESETS`, die alle im Trainings-Split liegen (das Modell kennt diese Prompts
wörtlich). "Ungesehen" = `candy kingdom`, `swamp witch coven` (Test-Split, nie trainiert). Der Vergleich mit Groq
ist auf "gesehen" fair, "ungesehen" ist der ehrliche Generalisierungswert. Eine Lücke zwischen beiden gibt es
in keinem Lauf - weder bei der Gültigkeit noch bei der Diversität.

**Wichtige Einschränkung:** Der Harness misst Vielfalt, nicht Qualität. Dass Lauf 1 + Beschränkung mehr
verschiedene Namen erzeugt als Groq, heißt nicht, dass es die besseren Namen sind - nur, dass es sich
seltener wiederholt.

## Lauf 1: was schiefging, und wie wir es eingegrenzt haben

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

## Lauf 1, Notlösung: schema-beschränktes Decoding

Ollamas `format`-Parameter (`src/agentic_rogue_like/agent/ollama_model.py`, Flag `--constrained` im Eval) übersetzt das
`EnemyProposal`-Schema in eine Grammatik. Bei jedem Token sind nur noch Fortsetzungen erlaubt, die zum Schema
passen; ein Objekt ohne `attack_name` kann nicht mehr geschlossen werden. Dasselbe Modell, derselbe Prompt, keine
Zusatzlatenz (3,6 s mit und ohne). **Es bringt dem Modell nichts bei** und prüft das Budget nicht - dass alle 604
Antworten im Budget lagen, ist eine echte Leistung des Fine-Tunes. Durch Lauf 2 überholt (siehe unten), aber als
Fallback-Mechanismus weiterhin nützlich, siehe "Offene Fragen".

**Wichtige Einschränkung, gilt für jeden 100-%-Vergleich in diesem Dokument:** Groq erzwingt sein Schema *nicht*
hart - es übergibt es als Tool-Definition, und wir haben bei der Datengenerierung selbst `tool_use_failed`-Fehler
gesehen (~1-2 %). "100 % gegen ~99 %" ist deshalb kein reiner Qualitätsgewinn, sondern teilweise ein
Konstruktionseffekt: strukturelle Gültigkeit ist mit Beschränkung garantiert, bei Groq nicht. Belastbar gemessen
sind Budget-Treue, Diversität und Latenz.

## Lauf 2: die Ursache behoben, ein neues Problem sichtbar gemacht

**Was geändert wurde** (aus der Lauf-1-Diagnose abgeleitet, kein Sweep):

- **Loss nur auf der Antwort** (Prompt/Completion-Format statt Textfeld) - in Lauf 1 zählte der fast
  konstante Prompt (~72 % der Tokens) beim Fehler mit, das Lernsignal für die Antwort war entsprechend dünn.
- **LoRA auf allen linearen Schichten** statt nur Attention: 18,5 statt 4,4 Mio. Parameter (1,2 % statt
  0,28 %). Begründung: Lauf 1 zeigte Unter-, nicht Überanpassung (Val-Loss sank bis zuletzt), also mehr
  Kapazität statt weniger.
- **5 statt 3 Epochen**, Early-Stopping-Geduld 2 statt 1.
- Prompt, Rang (16), Alpha (32), Dropout (0,05) und Lernrate (2e-4) unverändert.

**Ergebnis:** 100 % gültige Antworten, ganz ohne Beschränkung, auf 300 gesehenen und 304 ungesehenen
Aufrufen - kein einziges fehlendes Feld mehr. Der Notbehelf aus Lauf 1 ist für dieses Problem nicht mehr
nötig.

**Neuer Befund - Diversität eingebrochen.** Im JSON der Antworten selbst nachgesehen (nicht nur die
aggregierte Metrik):

- **Early-Tier, gesehene Settings: alle 75 Antworten hatten exakt `hp=32`.** Kein einziger anderer Wert.
- Unter allen 300 gesehenen Antworten kommt der Name **"Neon Wraith" 38-mal vor (12,7 %)**, "Crystalline
  Maw" 15-mal - von 300 Antworten nur 135 verschiedene Namen (Lauf 1 mit Beschränkung: 285 von 300).
- Die Angriffs-Diversität (0,78 / 0,81) und die zuvor komplett fehlende Elite-Streuung (jetzt 0,90 / 0,99,
  vorher 0,00) haben sich dagegen verbessert - der Einbruch betrifft vor allem Namen und HP-Werte, nicht
  alles gleichermaßen.

**Verdacht damals:** dieselben zwei Stellschrauben, die das Gültigkeitsproblem behoben haben - mehr
LoRA-Kapazität *und* mehr Trainingsschritte auf nur 217 Beispielen. Beide zusammen sind ein klassisches
Rezept dafür, dass sich ein Modell auf wenige, im Training häufig belohnte Muster einschießt. Welche der
beiden es war, klärt Lauf 3.

## Lauf 3: Kapazität von Trainingsdauer getrennt

Lauf 2 hatte gegenüber Lauf 1 drei Dinge gleichzeitig geändert, also war nicht zuzuordnen, welche Änderung
die Diversität gekostet hat. Die Loss-Maskierung blieb (sie hat das eigentliche Problem gelöst), übrig
blieben Kapazität und Dauer als Verdächtige. Lauf 3 hält **alles aus Lauf 2 bis auf die Epochen**: wieder
3 statt 5, Early-Stopping-Geduld 1 statt 2. Ein gezielter Test einer Hypothese, kein Sweep.

**Ergebnis: an der Trainingsdauer lag es nicht.**

| | Lauf 2 (5 Epochen) | Lauf 3 (3 Epochen) |
|---|---|---|
| Gültige Antworten | 100 / 100 % | 96,7 / 99,3 % |
| Eindeutige Namen | 0,45 / 0,56 | 0,56 / 0,52 |
| Anteil häufigster Name | 12,7 / 6,6 % | 6,2 / 13,2 % |
| Verschiedene HP-Werte je Tier | 1/3/6/2 | 1/3/6/2 |

Die Diversität bleibt praktisch unverändert - der early-Tier kollabiert weiterhin auf einen einzigen
HP-Wert, und die Unique-Quoten schwanken in beide Richtungen, ohne Trend. Gleichzeitig kostet die kürzere
Trainingszeit etwas Gültigkeit. Damit bleibt als Ursache die **LoRA-Kapazität** (alle linearen Schichten
statt nur Attention) beziehungsweise die Kombination aus Kapazität und Antwort-Loss - nicht die Dauer.

**Und der eigentliche Befund:** Stellt man alle Varianten nebeneinander (Tabelle oben), gewinnt ausgerechnet
die vermeintliche Krücke. Lauf 1 + Beschränkung ist schemakonform per Konstruktion **und** hat die mit
Abstand beste Diversität: 0,95 eindeutige Namen gegen 0,45-0,56, häufigster Name 1,0 % gegen 6-13 %,
4/4/9/7 verschiedene HP-Werte gegen 1/3/6/2. Selbst gegenüber Groq (0,67 / 12,7 % / 5/4/7/7) steht es besser
da.

**Erklärungsversuch (Hypothese, nicht gemessen):** Der Attention-only-Adapter aus Lauf 1 hat das Modell kaum
verschoben - es blieb nah an der breiten Verteilung des Basismodells und konnte nur das Format nicht
zuverlässig treffen. Genau diese eine fehlende Eigenschaft liefert die Grammatik-Beschränkung nach, ohne die
Inhaltsverteilung anzufassen. Lauf 2 und 3 haben das Format dagegen *eintrainiert* und dabei zusammen mit dem
Format auch das enge Vokabular und die konkreten Zahlenwerte der 217 Beispiele übernommen. Formulierung für
den Merksatz: Ein Decoder-Constraint erzwingt Struktur, ohne Vielfalt zu kosten; Training erzwingt Struktur,
indem es Vielfalt kostet.

**Konsequenz für die Produktion:** `DEFAULT_MODEL_NAME` in `src/agentic_rogue_like/agent/ollama_model.py`
zeigt auf `qwen2.5-enemy-generator` (Lauf 1), und `_model()` setzt `constrain_output=True`. Die Beschränkung
bleibt auch dann an, wenn per `ENCOUNTER_AGENT_OLLAMA_MODEL` ein anderes Modell gewählt wird: Für Modelle,
die sie nicht brauchen, kostet sie nichts messbares (gleiche Latenz), schließt aber einen kompletten
Fehlermodus aus.

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

Lauf 2 und 3 nutzen dieselbe Daten-/Modellbasis und denselben Merge-/Quantisierungs-Ablauf; ihre Änderungen
sind oben in den jeweiligen Abschnitten aufgeführt. Ollama-Modelle: `qwen2.5-enemy-generator` (Lauf 1,
Voreinstellung), `-v2`, `-v3` sowie `-f16`/`-v2-f16` als unquantisierte Diagnose-Varianten.

## Offene Fragen

- **Warum genau die höhere LoRA-Kapazität die Vielfalt kostet**, ist nicht gemessen, nur plausibel erklärt
  (siehe Lauf 3). Ein Mittelweg wäre testbar, etwa all-linear bei Rang 4 oder 8 statt 16, oder
  Attention-only mit Antwort-Loss - also Format lernen, ohne so viel Verteilung zu verlieren. Beides je ein
  gezielter Lauf, kein Sweep.
- **Schema-Beschränkung zusammen mit Lauf 2/3** wurde nicht gemessen. Sie dürfte deren Diversität nicht
  verbessern (sie erzwingt Vollständigkeit, nicht Abwechslung), aber ungeprüft ist ungeprüft.
- **Ob die höhere Namensvielfalt von Lauf 1 auch bessere Namen bedeutet**, misst der Harness nicht. Dafür
  bräuchte es ein Qualitätsurteil, etwa ein LLM-as-judge gegen die Groq-Antworten oder schlicht Hinsehen.

## Einsatzbereich: lokal, nicht deployed

Der `ENCOUNTER_AGENT_MODEL_SOURCE=ollama`-Switch funktioniert nur, wenn Spiel-Engine und Ollama-Server auf
derselben Maschine laufen (`localhost:11434`) - also für lokales Spielen/Entwickeln, nicht automatisch für
die nach Azure Container Apps deployte Version. Bewusste Entscheidung, **nicht** für Azure einzurichten:

- Das aktuelle Deployment kann bei Inaktivität auf null Instanzen herunterskalieren, weil ein Groq-Aufruf
  kaum Speicher/CPU braucht - kostet im Leerlauf praktisch nichts.
- Ollama bräuchte das Modell dauerhaft im Speicher (sonst ~3-4s Nachladezeit pro Kaltstart), also mindestens
  eine dauerhaft laufende Instanz. Grob überschlagen (2 vCPU/4 GiB, Azure-Idle-Tarif, Stand 2026-09):
  ~$50/Monat, abzüglich eines kleinen Anteils aus dem kostenlosen Kontingent (180.000 vCPU-Sekunden/Monat).
  Nur eine Größenordnung, keine belastbare Kalkulation - abhängig von echter Auslastung/Konfiguration.
- Damit ist der Kostenvorteil aus dem Vergleich oben ("$0 statt $0,15/1000 Aufrufe") **nur lokal gültig**.
  In Azure würde er sich umkehren: Groqs Cent-Beträge gegen niedrige zweistellige Dollar-Beträge pro Monat,
  nur um Latenz zu sparen.

## Bekannte Lücken und Vorbehalte

- **Kosten** gemessen aus Tokenzahlen (320,6 ein / 427,8 aus pro Aufruf, gemittelt über alle 4 Tiers) mal
  Groq-Listenpreis vom 2026-09-17; Hardware und Strom des lokalen Modells sind nicht eingerechnet.
- **Latenz** sequenziell, eine Anfrage nach der anderen, Groq über das Netz, Ollama auf deiner CPU.
- **Stichprobengröße:** bei n~300 liegt die Unsicherheit einer Rate um 50 % bei etwa ±3 Prozentpunkten, bei den
  n=80-Diagnoseläufen bei ±5. Die Groq-Tiers early (118) und mid (42) sind unterschiedlich groß, weil sie aus
  zwei zusammengeführten Läufen stammen (ein Überschreibungs-Bug im Eval-Harness kostete einen Teil des
  ersten mid-Laufs, seither behoben, siehe `eval/report.py`).
- **Frühe Diversitäts-Warnung bestätigt als Stichprobenartefakt:** die allererste Messung (n=25) zeigte bei
  Groq-Boss-Gegnern Attack-Streuung 0,0; mit der vollen Stichprobe (n=75) liegt sie bei 0,80 - kein echter
  Befund. Lauf 1 des Fine-Tunes hatte dasselbe Muster bei Elite-Gegnern, dort aber bei n=75 immer noch 0,0 -
  das war also ein echter Befund, den Lauf 2 behoben hat (jetzt 0,90 / 0,99). Der aktuelle Diversitäts-Befund
  aus Lauf 2 (Namen/HP-Werte, siehe oben) ist mit n=300/304 groß genug, um ebenfalls kein Stichprobenrauschen
  zu sein.
