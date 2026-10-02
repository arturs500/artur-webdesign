# Sniper (holder-scorer) – Prüfung, Ursachen, Umbau, Handy-Alarme

Stand: **2026-09-29**. Gegenstand: das Werkzeug `tools/holder-scorer` (Stand des geschlossenen PR #1, Commit
60dacb8, unverändert übernommen in Commit e5364e6; Fixes in Version 0.3.1 im Folge-Commit). Grundlage: zwei
unabhängige Code-Reviews (Signallogik/Datenkorrektheit; Alarm-Pipeline/Papier-Trading/Protokollierung) mit
Sonden (Simulationen gegen den echten Code), eigene Prüfungen (kein Trading-Code, 72 Bestandstests, 8 neue
Tests) sowie die am 2026-09-29 direkt geprüften Pump.fun-Fakten aus `PREREGISTRATION_EXP002.md`.

Regeln des Projekts gelten unverändert: Edge-First, Paper-only, kein Bot-Bau, keine Käufe, keine API-Keys im Repo.
Das Werkzeug enthält keinen Code, der Transaktionen signiert oder sendet (geprüft per Suche nach
`sendTransaction`, `Keypair`, `sign`, `private_key`; keine Treffer). Es liest, bewertet, alarmiert und rechnet
auf dem Papier. Alarme aufs Handy sind damit **Beobachtungen einer Call-Quelle unter Test**, keine Kaufsignale.

**Grenze dieser Prüfung:** Deine tatsächlich gesendeten Calls liegen nicht vor (keine `live.jsonl`,
`papier.jsonl` oder Telegram-Exporte im Repo, OQ-024). Geprüft wurden Regeln, Code und Datenpfad; die
Aussage "was falsch war" ist deshalb eine **Ursachenanalyse des Mechanismus**, keine Auswertung deiner Historie.
Sobald du Aufzeichnungen lieferst, lässt sich jeder Call mit den Mitteln aus Abschnitt 5 nachrechnen.

---

## 0. Kurzfazit

1. Der Score misst in den ersten 90 Sekunden vor allem das **Alter** eines Tokens, nicht seine Qualität: vier
   der sieben Faktoren (65 von 100 Punkten, genau die GO-Schwelle) sind für praktisch jeden jungen Token mit
   ein paar Kleinkäufen automatisch voll. Ein GO heißt faktisch: "6 bis 12 fremde Wallets haben in unter zwei
   Minuten 0,5 bis 1 SOL netto gekauft, und nichts Sichtbares ist rot".
2. Damit ist jeder GO ein **Follower-Trigger auf öffentliche Information**: Die Käufe, die den Alarm auslösen,
   haben den Kurvenpreis bereits bewegt; Bots sehen dieselben Käufe 1 bis 2 Sekunden früher, ein Mensch mit
   Telegram-Push handelt 45 bis 100 Sekunden nach dem Launch. Die im README selbst zitierte Auswertung von 266
   Einstiegsvarianten auf 63 000 Launches fand keinen einzigen Einstieg auf sichtbare Käufer mit unterer
   Konfidenzgrenze über null nach Gebühren.
3. Auf der Bonding Curve ist die Rechnung hart: Ein Hin und Zurück ohne Kursbewegung kostet 2,5 %; ein 2x
   bei Einstieg nach 2 SOL Zufluss braucht **weitere 13,9 SOL** Nettozufluss anderer. Die einzige kausale
   Größe für die Rendite eines Followers ist der künftige Nettozufluss anderer **minus** der Abfluss der
   Insider (Dev, Bundle, Erstkohorte). Genau das misst der Score kaum, den Überhang der Insider nur teilweise.
4. Dazu kommen Datenfehler, die **falsche Alarme** erzeugen (verzögerte Holder-Daten → falscher DEV-DUMP/RUG;
   falsche Creator-Adresse bei Holder-Rewards-Coins; unsichtbare Bundles im Create-Slot), ein **stiller
   Widerruf** (nach BLICK sperrte der Scorer intern, das Handy erfuhr nichts), eine **unzuverlässige
   Telegram-Zustellung** (Fehler verschluckt, Reihenfolge nicht garantiert) und ein **falsches Erfolgsmaß**
   (Holder-Wachstum statt Rendite), das Verlust-Calls als Treffer zählt.
5. Umbau daher nicht "Gewichte drehen", sondern: jeden Alarm zu einem prüfbaren Datensatz machen (Slot,
   Kurvenstand, Regelversion, Tape), Rendite statt Holder als Ziel, Kontrollgruppe, menschliche Latenz, und
   erst mit Evidenz aus einigen hundert Alarmen entscheiden, ob es eine Call-Quelle mit Edge ist (EXP003).

---

## 1. Was der Sniper tut – die Kette

```
PumpPortal-Stream (Launch)  ──►  Token abonnieren  ──►  RPC logsSubscribe (Trades als "Program data")
        │                                                        │
        ▼                                                        ▼
  synthetischer Dev-Kauf, Kurvenstand aus Frame          Trade-Events dekodieren, Kurve aktualisieren
        │                                                        │
        └────────────►  Merkmale (features.py)  ◄────────────────┘
                        Außen-Käufer, Zufluss 120 s, Holder-Momentum, Bundle-Anteil (Slot ≤ create+4),
                        Dev-Anteil/-Verkauf, Top-10, frische Wallets, Creator-Historie, Socials
                                   │
                                   ▼
                        Score (7 Faktoren, K.-o.-Regeln, Mindestmengen)  ──►  Wort: GO/WARTE/FRÜH/NEIN/RUG/TOT
                                   │
                                   ▼
                        Alarme (live.py): 👀 BLICK (≥5 Außen-Käufer, ≥0,5 SOL, ≤60 s, kein Veto)
                                          🟢 GO (Wort GO, kein Veto, Zufluss > 0)
                                          🔴 RUG/⚫ TOT (Kippen nach BLICK/GO, MC −35 % seit GO)
                                          ↩️ WIDERRUF (neu: weiches Veto nach BLICK)
                                   │
                                   ▼
                        Telegram (Handy)  ──►  Mensch liest, öffnet Chart, entscheidet
```

**Latenzbudget bis zum Handy** (Review-Schätzung aus dem Code; kein Live-Test):

| Schritt | Latenz |
|---|---|
| Block → PumpPortal-Frame | 0,5–2 s (fremder Indexer, keine Garantie, kein Replay bei Reconnect) |
| Abonnement `logsSubscribe` nach dem Launch | 0,1–0,5 s; Trades im Create-Slot und den folgenden Slots werden **nie** geliefert |
| Trade-Benachrichtigung (`confirmed`) | 0,5–1,5 s nach dem Trade-Slot |
| Bewertung (Tick) | 0–1 s; Stufe 2: GO frühestens 20 s Alter, typisch 25 s |
| Telegram-API + Push | 1–6 s |
| Mensch (lesen, Chart, Entscheidung) | 15–60 s |
| **Summe** | BLICK ≈ Launch + 8–25 s; GO ≈ Launch + 25–45 s; **Einstieg eines Menschen ≈ Launch + 45–100 s** |

Das Papier-Trading rechnete bisher mit 2 s Latenz. Es misst damit einen Bot, nicht dich.

---

## 2. Was an den Calls falsch war – Ursachen statt Symptome

### 2.1 Der Score misst Alter, nicht Qualität (Sonde am echten Code)

Konfiguration Stufe 2, Token 25 s alt, Dev 2 %, n Käufer à 0,05 SOL, kein Bundle, Creator ohne Historie,
zwei Social-Links: n = 3 → Score 86; n = 6 oder 8 → **91**; n = 12 → GO. Zusammensetzung bei n = 8:
Momentum 25/25 (8 neue Käufer bei 9 Holdern), Kaufdruck 15/15 (**null Verkäufer, weil noch niemand verkaufen
konnte**), Verteilung 20/20 (Top-10 ist bei 2 % Float immer klein), Organisch 5/5, Dev 7/10, Socials 10/10.

Kausal heißt das: Die Faktoren "Kaufdruck ohne Verkäufer" und "Verteilung auf Supply-Basis" sind
**Alterseffekte**, das Momentum arbeitet mit Kleinstnennern. Der Score diskriminiert früh nichts; die
Entscheidung fällt allein an den Mindestmengen (6 Käufer, 0,5 SOL). "GO" ist damit kein Qualitätsurteil,
sondern ein Zähler.

### 2.2 Ein GO ist ein Follower-Trigger

Die Bedingungen für GO (sichtbare Außen-Käufer, positiver Zufluss, Holder-Momentum) sind **Symptome desselben
Flusses, der den Kurs schon bewegt hat**. Wer darauf kauft, kauft die zweite Welle nach ihrem Anstieg. Schneller
sind: Bots, die denselben Dev oder dieselben Wallets verfolgen, und alle, die die Log-Zeile 1 bis 2 Sekunden vor
dem Telegram-Push sehen. Das README zitiert die passende Evidenz selbst (Abschnitt "Was über solche Calls schon
bekannt ist"): 266 Einstiegsvarianten auf 63 000 Launches, **keine** mit unterer Konfidenzgrenze über null; die
Latenz zwischen Signal und Kauf kostet 5 bis 16 Prozentpunkte je Trade. Bundle-, Konzentrations- und Ring-Filter
verkleinern Verluste, erzeugen aber keinen Gewinn.

### 2.3 Die Kurvenmathematik lässt wenig Spielraum

Konstantprodukt auf virtuellen Reserven: Preis = vS/vT = vS²/k. Das Kursvielfache zwischen zwei Zeitpunkten ist
exakt (vS_exit / vS_entry)². Sonde mit 0,08 SOL und 1,25 % Gebühr je Seite: Einstieg nach 2 SOL Zufluss
(MC 31,8 SOL) → Hin und Zurück sofort −2,47 %; Break-even braucht +0,4 SOL weiteren Nettozufluss, **2x braucht
+13,9 SOL, 3x +24,2 SOL**; nach 10 SOL Zufluss (MC 49,7 SOL) braucht 2x +17,3 SOL. Nicht modelliert waren
Priority-Fees (0,0005–0,002 SOL je Seite = 1,25–5 % des Einsatzes bei 0,08 SOL), die Token-Account-Einlage
(≈ 0,002 SOL = 2,55 %, rückholbar) und fehlgeschlagene Transaktionen. Bei kleinen Einsätzen ist das der
dominante Kostenblock, nicht die Kurvengebühr.

Folge: Jede Qualitätsaussage des Scores ist für die Rendite zweitrangig. Kausal zählt nur, ob **nach** dem eigenen
Einstieg mehr Netto-SOL von anderen kommt, als die Insider (Dev, Bundle-Wallets, Erstkohorte mit Einstand weit
unter dem aktuellen Kurs) herausnehmen. Der Insider-Überhang ist die einzige Größe im Werkzeug, die in diese
Richtung misst, und sie wird nur lückenhaft erfasst (Abschnitt 2.4).

### 2.4 Falsche Alarme aus Datenfehlern

| Ursache (Datei) | Wirkung auf die Calls | Status |
|---|---|---|
| Verzögerte DAS-Holderdaten wurden als vollständig behandelt: fehlt die Dev-Wallet im noch nicht indexierten Ergebnis, wird "Dev hat 100 % verkauft" berechnet (features.py, Dev- und Bundle-Anteile aus DAS) | falscher DEV-DUMP / Bundle-Exit → **falscher RUG-Alarm**, Token verworfen | **behoben 0.3.1**: DAS nur, wenn es ≥ 90 % des Floats abdeckt |
| Holder-Rewards-Coins (seit 2026-09-12) tragen als `creator` eine Programm-Adresse; der Sammelmodus scannte deren Historie (collect.py) | Serien-Deployer unsichtbar, Creator-Faktor geschenkt, RPC-Budget verschwendet | **behoben 0.3.1**: Signer als Creator, wenn `is_holder_reward` |
| Der Live-Modus abonniert Trades erst nach dem Launch: Käufe im Create-Slot und den ersten Slots kommen nie an; Bundles werden nur indirekt über UNSICHTBAR (≥ 2 % Supply) erkannt | Bundles unter 2 % laufen als sauberer Token durch; Bundle-Wallets zählen bei geratenem Create-Slot als Außen-Käufer | offen (Umbau P2: Create-Slot-Transaktionen einmal nachladen) |
| Stufe 3: Bundle-Grenze 15 % gilt nur für BLICK; GO prüft weiterhin 10 % (quick.py) | README versprach etwas anderes | README korrigiert; Verhalten belassen |
| Preis für USDC-quotierte Kurven durch 1e9 statt 1e6 (pump.py, paper.py) | Papier-Strategien konnten USDC-Coins mit 1000-fach falschem Preis "handeln" | **behoben 0.3.1**: Papier-Trading handelt nur SOL-Kurven |
| Ereignis-Layout hinter den Reserven (Fee-Felder, Mayhem, Quote) nur zirkulär getestet, Fee-Felder verworfen | stille Fehldekodierung bei Layoutänderung; Papiergebühr konstant statt aus dem Event | offen (Umbau P1: echte Transaktions-Fixtures, Gebühr aus dem TradeEvent) |
| Zwei Uhren: Alter aus Empfangszeit, Trades aus Chain-Zeit; Latenz als 2 s angenommen statt gemessen | Alter, Fenster und Einstiegspreis verschoben; Edge-Schätzung zu optimistisch | offen (Umbau P2: Slot als Zeitachse) |

### 2.5 Stiller Widerruf

Nach einem 👀 BLICK konnte ein weiches Warnsignal auftreten (SCHNELL, FRISCH, FUNDER, UNSICHTBAR, DEV-GROSS,
Bundle über der Grenze). Der Scorer sperrte GO intern, sendete aber nichts: Der Nutzer saß auf einem veralteten
BLICK. Nur harte K.-o.-Regeln (SERIE, DEV-DUMP) und Stillstand erzeugten RUG/TOT. **Behoben 0.3.1:** neuer Alarm
↩️ WIDERRUF, einmalig, mit den auslösenden Warnungen im Text (Test `test_widerruf_after_blick_when_a_soft_veto_appears`).

### 2.6 Telegram-Zustellung ohne Rückmeldung

Jede Nachricht startete einen eigenen Thread, der Rückgabewert wurde ignoriert: HTTP 429, Timeouts und Fehler
gingen stumm verloren, ein RUG konnte den GO überholen. **Behoben 0.3.1:** eine Sende-Warteschlange
(Reihenfolge, Wiederholung mit `retry_after`, Fehlerzähler, Statuszeile am Ende).

### 2.7 Alarmflut

Nach dem Rechenmodell des README (400 synthetische Launches, hochgerechnet auf 1 000 Launches je Stunde) erzeugt
Stufe 2 etwa 80 BLICK und 90 GO **je Stunde**, Stufe 3 rund 200 Nachrichten je Stunde. Für ein Handy ist das
unbrauchbar: eine Nachricht alle 20 Sekunden macht jeden Call wertlos, weil niemand ihn liest. Stufe 1 mit nur
GO/RUG liegt bei etwa 20 GO je Stunde. "Organisch" heißt im Modell nur "keine Rug-Mechanik", nicht "gestiegen".

### 2.8 Das Erfolgsmaß war falsch

`outcome`/`evaluate` prüfen "Holder-Zahl ×1,5 nach 15 Minuten" – gemessen **zum Zeitpunkt des Prüflaufs** (nach
zwei Tagen misst man Holder nach zwei Tagen), mit einer Basis aus den seit Abonnement gesehenen Trades und einem
Später-Wert aus DAS über alle Holder (Äpfel gegen Birnen). Kausal ist Holder-Zahl ein Ratschenzähler: Bagholder
verkaufen Staub nie, ein Dev-Dump in viele kleine Käufer **erhöht** die Holder-Zahl, während der Kurs kollabiert.
Der schlechteste Call wird so als "gewachsen" gezählt. **Teilweise behoben 0.3.1:** `outcome` markiert Prüfungen
lange nach dem Horizont als `stale`. Das eigentliche Ziel (Rendite aus Tape und Kurvenmathematik) ist Umbau P0.

### 2.9 Die Statistik belohnte Überanpassung

Der Papier-Report wählt die beste von 64 Regeln (Ziel × Stop × Zeit) und die beste von 12 Strategien ohne
Korrektur; der Was-wäre-wenn-Rechner verkaufte exakt zum Zielkurs ohne Latenz und Impact, der Startbucket enthielt
Kurse **vor** dem Einstieg (Stop-Loss durch ein Tief, das vor dem Kauf lag), und der Rückblick stieg zum **nächsten
Trade nach** dem Call ein (kauft dessen Bewegung mit). Ein Bootstrap-Intervall auf i.i.d.-Basis ignoriert
Marktregime und die Korrelation der Strategien über dieselben Token. **Behoben 0.3.1:** Startbucket und
Rückblick-Einstieg (Tests `test_simulate_rule_ignores_prices_before_the_entry_in_its_first_bucket`,
`test_look_back_enters_on_the_curve_as_it_stood_at_call_plus_latency`). Offen: Vorregistrierung der Regeln,
Zeitsplit mit Konfidenzintervall, Block-Bootstrap (Umbau P1).

### 2.10 Das Protokoll ließ keine Nachprüfung zu

Ein Alarm-Record enthielt Wort, Flags, Score, Faktoren und Merkmale, aber weder Slot noch Kurvenstand, weder
Creator noch Regelversion, keine Datenqualitätsfelder; `__version__` (0.2.0) widersprach `pyproject.toml`
(0.3.0). Damit war nie rekonstruierbar, unter welchen Regeln ein Call entstand und wie die Kurve stand.
**Behoben 0.3.1:** jeder Record trägt Version, Regel-Hash (SHA-256 über alle Schwellen), Slot, Kurvenstand
(virtuelle/reale Reserven), Creator, Name/Symbol/URI, `create_slot_known`, `window_guessed`, gesehene Trades,
offene Nachlade-Signaturen; mit `--tape` wird jeder gesehene Trade eines Tokens mit Alarm (Slot, Reserven,
Gebühr) angehängt, rückwirkend ab dem ersten Alarm.

---

## 3. Was mit deinen Logs möglich wird (OQ-024)

Wenn du `live.jsonl`, `papier.jsonl` oder eine Liste `mint, Unix-Zeit, Alarmstufe` lieferst (Ablage
`data/sniper/`), lässt sich je Call rechnen: Kurvenstand bei Call + 30 s (Mensch) und + 2 s (Bot), Netto-Rendite
nach 60/300/900 s mit Kurvengebühr und Kostenmodell aus EXP002, Anteil Graduation, Anteil Insider-Abfluss nach dem
Call, und der Vergleich mit zufälligen Launches gleichen Alters und Fortschritts (Kontrollgruppe). Für Alarme vor
Version 0.3.1 fehlen Slot und Reserven im Record; sie müssen per `paper rueckblick` aus der Kette nachgeladen
werden (teuer: tausende `getTransaction` je Token, mit Helius-Kontingent für 20 bis 50 Calls vertretbar).

---

## 4. Was in Version 0.3.1 und 0.3.2 geändert wurde

| Änderung | Wirkung | Test |
|---|---|---|
| **0.3.2** Präzisions-Gate (`profile.py`): BLICK/GO nur bei neuen Haltern in den letzten 15 s (Stufe 1 ≥ 3, sonst ≥ 2); GO mit `--profil` nur bei Ähnlichkeit ≥ 0,7 zum Profil gespeicherter guter Coins am gleichen Checkpoint (10/20/30/45 s); Kopfzeile `Halter +4/15s · Profil 80 % (MC↑)`; Zähler `go_profil` | weniger GO auf Coins, die gerade keine neuen Halter gewinnen oder nicht wie die gespeicherten guten starten; null zusätzliche RPC-Aufrufe | `test_live_gate_needs_holder_rise_and_profile_similarity` |
| **0.3.2** `profil bauen` aus Tape/Records/Papier (ohne RPC) oder Mint-Liste (RPC, gedeckelt): Frühvektoren je Checkpoint, Rendite-Label wie `tape report`, Bänder 10.–90. Perzentil der guten Coins, Gewichte aus der Trennung zu schlechten Coins, Zeitsplit-Prüfung mit Wilson und Block-Bootstrap; `profil zeigen` | der Ähnlichkeitsfilter ist aus eigenen Daten gebaut und auf späteren Daten geprüft statt geglaubt | `test_build_profile_from_tape_labels_saves_loads_and_checks`, `test_label_from_rows_…`, `test_fetch_ticks_…` |
| **0.3.2** Records, Papier-Kontext und Tape tragen die Frühvektoren bzw. den Dev (`profil`, `dev`) | jeder künftige Alarm liefert Material für das nächste Profil | `test_live_gate_…` (Record), `test_early_vector_…` |
| Alarm-Records mit Version, Regel-Hash, Slot, Kurvenstand, Creator, Datenqualität (`calibrate.alert_record_extra`, `rules_hash`) | Calls sind nachrechenbar und Regelstände trennbar | `test_alert_record_extra_carries_slot_curve_and_rule_version` |
| `--tape DATEI`: jeder gesehene Trade eines Tokens mit Alarm, rückwirkend ab dem ersten Alarm | Offline-Replay jeder Latenz und Regel ohne `getTransaction` | `test_tape_backfills_at_first_alert_and_streams_afterwards` |
| ↩️ WIDERRUF nach BLICK bei weichem Veto | kein veralteter 👀 auf dem Handy | `test_widerruf_after_blick_when_a_soft_veto_appears`, `…_not_sent_without_tier_or_after_go` |
| Telegram-Warteschlange mit Reihenfolge, Wiederholung bei 429, Fehlerzähler | keine stummen Verluste, RUG nicht vor GO | `test_telegram_sender_retries_on_429_and_keeps_order`, `…_counts_lost_messages` |
| DAS-Holderdaten nur bei ≥ 90 % Float-Abdeckung | keine falschen DEV-DUMP/RUG durch Index-Verzögerung | Bestandstests (72) unverändert grün |
| Holder-Rewards: Signer als Creator | richtige Creator-Historie | – (Fixture ohne Netz nicht verfügbar, siehe Umbau P1) |
| Papier-Trading: keine USDC-Kurven; Startbucket ohne Vor-Einstiegs-Kurse; Rückblick-Einstieg zum Kurvenstand vor dem Einstieg | weniger optimistische Papierergebnisse | `test_simulate_rule_…`, `test_look_back_…` |
| `outcome` mit `horizon_s` und `stale` | Holder-Prüfungen weit nach dem Horizont sind erkennbar | – |
| `sig_meta` im Live-Snapshot leer statt erfunden | `failed_after_30s_share` ist nicht mehr fälschlich 1,0 | Bestandstests |
| Version 0.3.1 in Paket und `pyproject.toml`; `.gitignore` um `.venv/`, `*.jsonl`, `.env`, `.secrets/` | Aufzeichnungen und Umgebungen landen nicht im Repo | – |
| `tape report` (Modul `replay.py`): Rendite-Label je Alarm aus Tape + Records, Latenz × Horizont, Kosten, Graduation zweifach, Kontrollgruppe, Wilson/Block-Bootstrap/Holm, Primärzeile vorab | Alarme sind als Call-Quelle objektiv prüfbar (Umbau P0.2/P0.3) | `tests/test_replay.py` (9 Tests) |
| `--tape-sample ANTEIL`: deterministische Kontroll-Stichprobe aller beobachteten Token im Tape; Zähler `dropped_full` bei vollem Tracking | Kontrollgruppe ohne zusätzlichen RPC-Aufwand; Ausfälle sichtbar | `test_live_tape_sample_tapes_control_tokens_without_alert` |

Bewusst **nicht** geändert: Gewichte und Schwellen des Scores (ohne Daten wäre das Raten), die Hypothese des
Werkzeugs, das Vokabular der Kurznachricht. Kein Trading-Code, keine Bot-Anbindung.

### 4.1 Präzisions-Gate 0.3.2: warum so und nicht anders

Auftrag: GO nur für Coins, die **innerhalb von Sekunden steigende Halterzahlen** zeigen und den im Papier-Sniper
**gespeicherten guten Coins gleichen**; sparsam mit dem Nutzungsvolumen, aber normal nutzen.

1. **Halter-Anstieg statt Halterzahl.** Die Zahl der Halter wächst mit dem Alter (Abschnitt 2.1); kausal für
   künftigen Zufluss ist, ob *jetzt* noch neue Wallets kaufen. Deshalb misst das Gate die Differenz der Halter
   (ohne Dev, Bestand über 1 000 Token) zwischen jetzt und 15 s davor, aus den abonnierten Log-Trades
   (`early_vector`). Ein Wallet, das kauft und sofort wieder verkauft, zählt nicht. Schwelle ohne Daten gesetzt
   (OQ-027), per `--holder-anstieg` änderbar.
2. **Ähnlichkeit zum gleichen Zeitpunkt, nicht zum Endzustand.** Gespeicherte gute Coins sehen am Ende anders aus
   als am Anfang; vergleichbar ist nur der Start. Darum liegen die Vektoren an festen Checkpoints nach dem ersten
   Trade (10/20/30/45 s), und der Live-Coin wird mit dem Band des größten Checkpoints ≤ seinem Alter verglichen.
   Alle Checkpoints liegen vor dem Einstieg des Labels (t0+60 s), damit kein Merkmal die Zukunft des Labels sieht.
3. **Was "gut" heißt, legt die Kurvenmathematik fest, nicht ein Gefühl.** Label wie in `tape report`: Einstieg
   t0+60 s zum Kurvenstand nach allen Trades dieser Sekunde, Ausstieg +180 s (Ende des 240-s-Fensters), Gebühr aus
   dem Trade, Kosten medium; gut = graduiert oder Netto-Rendite > 0. Papier-Ergebnisse (`pnl_pct`) zählen nur, wenn
   kein Tape-Label existiert; eine Mint-Liste kann Labels vorgeben (`gut`/`schlecht`).
4. **Bänder statt Modell.** Mit wenigen Dutzend Coins wäre ein Klassifikator Überanpassung mit Zahlen hinter dem
   Komma. Ein Band (10.–90. Perzentil der guten Coins) je Merkmal ist erklärbar ("MC↑" steht in der Nachricht), und
   das Gewicht eines Merkmals ist der Anteil schlechter Coins, den sein Band ausschließt (0,5 bis 1,0): Merkmale,
   die gute und schlechte Coins nicht trennen, zählen halb.
5. **Prüfung vor Glauben.** `--split 0.5` baut das Profil aus der früheren Hälfte der Coins und misst auf der
   späteren Hälfte Trefferquote (Wilson) und Renditedifferenz (Block-Bootstrap nach Stunde) zwischen "ähnlich" und
   "nicht ähnlich". Liegt das Intervall nicht über 0, trennt die Ähnlichkeit nichts; dann das Profil nicht laden.
6. **Nutzungsvolumen.** Live: keine neuen RPC-Aufrufe, nur Rechenzeit (Vektoren je Checkpoint werden gecacht).
   `profil bauen` aus Dateien: kein RPC. Nur `--mints` lädt Historie (Signatur-Seiten + getTransaction je Trade im
   Fenster), gedeckelt durch `--max-mints 20`/`--max-pages 10`, Schätzung mit `--dry-run`, Istwert in der Statuszeile.

Grenzen (OQ-027): Die Schwellen 2/3 Halter je 15 s, 0,7 Ähnlichkeit, 10 %-Quantil und das Label (60 s/180 s) sind
Startwerte ohne Daten. Das Profil lernt aus Coins, die der Sniper schon beobachtet hat (Alarme plus
Kontroll-Stichprobe): Es beschreibt, was *unter diesen* Coins gut lief, nicht alle Launches. Korrelierte Merkmale
(Zufluss, Zufluss der letzten 15 s, Kaufgröße) zählen mehrfach. Ein Band aus fünf Coins ist grob; mehr Aufzeichnung
ist der einzige Weg zu schärferen Bändern.

---

## 5. Umbau-Plan (kausal begründet, priorisiert, Paper-only)

**P0 – Jeder Alarm ist eine prüfbare Hypothese (Datengrundlage; 0.3.1 liefert die Felder)**

1. Alarm = Datensatz mit Regelversion, Slot, Kurvenstand, gesehenem Band (Tape). Erledigt in 0.3.1.
2. **Rendite-Label statt Holder-Wachstum:** Aus dem Tape per Kurvenmathematik (Konstantprodukt, Gebühr aus dem
   TradeEvent, eigener Impact, Priority-Fee-Szenarien wie in EXP002) die Netto-Rendite bei Einstieg **L ∈ {2, 10,
   30, 60} s** nach dem Alarm und Ausstieg nach festen Regeln (+60/+300/+900 s) berechnen. Holder-Wachstum nur noch
   beschreibend. **Erledigt in 0.3.1 (`tape report`, Modul `replay.py`):** Einstieg zum Kurvenstand bei Alarm + L
   (Worst-Case-Ordnung), Ausstieg auf den realen Kurvenstand plus eigenes Delta (Overlay; Replay der Folge-Trades
   bleibt P1), Kosten (Basisgebühr, Priority-Szenario low/medium/high, Token-Account-Einlage mit Rückholung),
   Graduation vor Ausstieg konservativ (0) und optimistisch, Trefferquote mit Wilson, Mittelwert mit Block-Bootstrap
   nach Alarmstunde, Holm über die sekundären Kombinationen, Primärzeile GO/+30 s/+300 s vorab festgelegt. TP/SL-Regeln
   sind bewusst nicht enthalten (Overfitting-Raster, siehe 2.9).
3. **Kontrollgruppe:** zufällige Launches gleichen Alters ohne Alarm, gleiche Simulation. Edge = Differenz zur
   Kontrolle, nicht absoluter Mittelwert (Konstruktion wie die Baseline in EXP002). **Erledigt in 0.3.1:**
   `--tape-sample 0.1` schreibt einen deterministischen Anteil aller beobachteten Token ab dem ersten Trade mit
   (Hash des Mints, unabhängig von Neustarts); `tape report` matcht je Alarm bis zu 5 Kontroll-Token mit Launch
   innerhalb von 6 h im gleichen Alter und berichtet die gepaarte Differenz mit Bootstrap-Intervall. Matching nach
   Kurvenfortschritt/Self-Buy wie in EXP002 ist noch offen.

**P1 – Statistik, die Überanpassung nicht belohnt**

4. Regeln und Strategien **vorregistrieren** (Datei mit Hash im Record), Report zeigt zuerst die vorregistrierten
   Regeln mit Konfidenzintervall; das 64er-Raster bleibt explorativ mit Zeitsplit (erste Hälfte wählt, zweite Hälfte
   berichtet **mit** Intervall) und Nennung von "k geprüft". Block-Bootstrap nach Stunde statt i.i.d.
5. **Menschliche Latenz als Standard:** `--paper-latency 30` im Telegram-Betrieb; Replay über mehrere Latenzen.
6. Decoder gegen **echte Transaktions-Fixtures** testen (klassischer Buy, create_v2/Mayhem, USDC, Holder-Rewards,
   Complete) statt zirkulär gegen den eigenen Encoder; Gebühr je Trade aus dem Event statt Konstante.

**P2 – Zuverlässigkeit**

7. Heartbeat alle 30 min (Launches, Trades, Alarme, Reconnects, Budget) und Stall-Alarm (3 min kein
   PumpPortal-Frame, 2 min keine Log-Benachrichtigung bei beobachteten Token) – heute nur Konsolen-Statuszeile.
8. Persistenz: gesendete Stufen, offene Papierpositionen, Pfade auf Platte; `flush` bei Ende (Waisen zählen);
   Zähler für verworfene Launches bei vollem Tracking.
9. **Create-Slot-Lücke schließen:** 2 s nach dem Launch einmal `getSignaturesForAddress(mint)` und die
   Create-Slot-Transaktionen nachladen (≈ 10 Einheiten) – erst dann ist das Bundle-Fenster beobachtet statt
   geraten. Slot als Zeitachse (`created_at` an die Blockzeit der Create-Tx angleichen); API-Key in Fehlermeldungen
   maskieren.
10. Budget: Standard 4 000 Einheiten je Stunde ≈ 2,9 Mio. je Monat übersteigt das kostenlose Helius-Kontingent
    (1 Mio. Credits je Monat [direkt geprüft, helius-labs/core-ai onboarding.md]) nach etwa zehn Tagen; danach
    fallen SERIE/SCHNELL/FRISCH/FUNDER und die Slot-Korrektur still weg. Für Dauerbetrieb im Free-Tarif
    `--budget 1000` (OQ-025).

**P3 – Signale kausal statt mechanisch (erst nach 2–4 Wochen Daten aus P0)**

11. **Streichen** (Alterseffekt oder trivial manipulierbar): voller Kaufdruck bei "keine Verkäufer" (neutral setzen),
    Verteilung auf Supply-Basis (auf Float-Basis rechnen), Organische-Käufe-Faktor ("klein = Mensch" stimmt nicht,
    Bump-Bots kaufen klein), Socials als Punkte (drei Strings), FAKE-MC/DÜNN für die Kurvenphase, Narrativ-Score als
    Einstiegsfilter, TOT-Finalisierung nach 25 s Stille (nur Flag).
12. **Umdrehen:** Dev-Kauf von 6,7–27 % gibt heute 90 % der Dev-Punkte ("aktiver Start"), blockt aber gleichzeitig
    GO über DEV-GROSS – widersprüchlich; Dev-Bestand ist Überhang, also negativ. "RUG" nur bei nachweisbarem
    Insider-Abfluss (Dev/Bundle/Kohorte verkauft ≥ X % und Netto-Abfluss), sonst `WARN <Grund>`.
13. **Neu messen** (kausal näher am künftigen Zufluss/Abfluss): Insider-Überhang = (Dev + Fenster-Wallets +
    Erstkohorte gehaltene Token) / Float; Anteil des Umlaufs in Wallets mit Einstand < 0,7 × aktueller Kurs
    (Verkaufsanreiz); Vorkauf-Float aus der Create-Tx und Slot 0…+4; Zufluss nur von Wallets mit Historie;
    Käufergrößen-Konzentration (Gini) und Anzahl unterschiedlicher Funder; **Latenzbudget** je Trade
    (Empfangszeit − Blockzeit): liegt der Median über 1–2 s, ist jeder Follower-Call strukturell zu spät.
14. **Jede Bedingung als Behandlung testen:** Rendite mit vs. ohne Bedingung bei gleichem Momentum-Bucket
    (gleiche Außen-Käufer/Zufluss). Nur was die Renditeverteilung bei gleichem Momentum verschiebt, ist eine
    Ursache und darf ins Regelwerk.

**Erfolgskriterium (Vorregistrierung EXP003, OQ-026):** "Sniper-Alarme als Call-Quelle" mit Hypothese, Fenster,
Kontrollgruppe, Latenz 30 s, Rendite aus Tape und Kurvenmathematik, Wilson-/Cluster-Bootstrap-Intervallen und
PASS/FAIL vorab – Struktur wie `PREREGISTRATION_EXP002.md`. Bis dahin sind Handy-Nachrichten Beobachtungen zur
späteren Auswertung, keine Handlungsaufforderung.

---

## 6. Handy-Alarme jetzt einrichten (Paper-only, keine Käufe, keine Keys im Repo)

1. **Konten:** Helius-Account (Free) → RPC-URL mit Key. Telegram: Bot bei @BotFather anlegen → Token; dem Bot eine
   Nachricht schicken, dann `https://api.telegram.org/bot<TOKEN>/getUpdates` aufrufen → `message.chat.id` ist die
   Chat-ID.
2. **Umgebungsvariablen** (nur in der Shell, nie in Dateien im Repo):
   ```bash
   export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=DEIN_KEY"
   export TELEGRAM_BOT_TOKEN="DEIN_BOT_TOKEN"
   export TELEGRAM_CHAT_ID="DEINE_CHAT_ID"
   ```
3. **Installation:** `cd tools/holder-scorer && python3 -m venv .venv && . .venv/bin/activate && pip install -e . websockets`
   (Python ≥ 3.10). Rauchtest ohne Netzlast: `python -m holder_scorer legend` und
   `python -c "from holder_scorer.notify import send_telegram; print(send_telegram('holder-scorer Test'))"` → `True`.
4. **Start für frühe Calls mit wenig Lärm, Free-Tarif-verträglich, mit Kontrollgruppe:**
   ```bash
   python -m holder_scorer live --stufe 1 --tiers go,widerruf,rug --notify go,widerruf,rug --telegram \
     --record live.jsonl --tape live_tape.jsonl --tape-sample 0.1 --budget 1000 --paper papier.jsonl --paper-latency 30
   ```
   Stufe 1 ≈ 20 GO je Stunde (Rechenmodell, kein Live-Test; mit dem Halter-Anstiegs-Gate aus 0.3.2 weniger);
   `--budget 1000` ≈ 720 000 Einheiten je Monat plus Websocket bleibt unter 1 Mio.; `--paper-latency 30` misst,
   was ein Mensch realisieren kann; `--commitment` auf `confirmed` lassen. Alternativ `--no-side` für null
   HTTP-Last (dann fehlen SERIE/SCHNELL/FRISCH/FUNDER und die Slot-Korrektur dauerhaft). Nach ein paar Tagen
   Aufzeichnung: `python -m holder_scorer profil bauen --tape live_tape.jsonl --records live.jsonl --papier
   papier.jsonl --out profil.json` (ohne RPC) und, wenn die Zeitsplit-Prüfung "trennt" meldet, den Start um
   `--profil profil.json` ergänzen (Abschnitt 4.1).
5. **Lesen der Nachricht:** 🟢 GO = "keine bekannte Warnung, genug fremde Käufer, gerade Zulauf" – ein
   Beobachtungsereignis, keine Kaufempfehlung; ↩️ WIDERRUF = BLICK vergessen; 🔴 RUG = Insider raus oder MC −35 %.
6. **Betrieb:** Statuszeile alle 60 s (Log-Benachrichtigungen, RPC-Einheiten, Budget-Auslassungen) und den
   Credit-Stand im Helius-Dashboard vergleichen; die Telegram-Statuszeile beim Beenden zeigt verlorene Nachrichten.
7. **Auswertung (wöchentlich):** zuerst `python -m holder_scorer tape report live.jsonl live_tape.jsonl` (Rendite-Label,
   Kontrollgruppe, ohne RPC); die Primärzeile zählt, der Rest ist Hinweis. Ergänzend `python -m holder_scorer outcome
   --file live.jsonl` (Holder-Label, nur beschreibend, Abschnitt 2.8) und `python -m holder_scorer paper report papier.jsonl`
   ("beste Regel" ignorieren, nur die Holdout-Zeile beachten). Aufzeichnungen nach `data/sniper/` legen (OQ-024), nicht
   committen, wenn sie Wallet-Adressen Dritter enthalten sollen.

---

## 7. Belege und Grenzen

- Code-Reviews vom 2026-09-29 (zwei unabhängige Prüfer, je ca. 30 Werkzeugaufrufe, Sonden gegen den echten
  Code: Score-Sättigung, Kurvenmathematik, Latenz, Startbucket-Look-back, Rückblick-Einstieg, `failed_after_30s`).
- Tests: 72 Bestandstests + 8 neue (`tests/test_edge_lab_fixes.py`), alle offline grün; `grep` nach Trading-/
  Signier-Code ohne Treffer.
- Pump.fun-Fakten (Programm-ID, Reserven, Gebühr 1,25 %, Diskriminatoren, Holder-Rewards-PDA, create_v2) wie in
  `PREREGISTRATION_EXP002.md` belegt [direkt geprüft, pump-fun/pump-public-docs].
- Nicht verifiziert: Helius-Websocket-Kosten "20 Credits je MB" (README-Angabe), Slot-Dauer 250 ms (Annahme im
  Code), das Rechenmodell der Alarmhäufigkeit (synthetische Launches). Keine Live-Daten in dieser Prüfung.
