# holder-scorer: Bekommt dieser Coin mehr Holder?

Ein Bewertungsmodul für pump.fun-Token auf Solana. Es sammelt On-Chain-Daten zu
einem Token, berechnet daraus mehrere Faktoren und gibt ein Urteil ab: **JA**
(wahrscheinlich mehr Holder), **UNKLAR** oder **NEIN**. Gedacht als Filter, der
vor dem Kauf in einen Sniper- oder Copy-Trading-Bot eingehängt wird, oder als
Werkzeug, das neben einem fertigen Bot mitläuft.

## Edge-Lab-Stand (2026-09-29)

Dieses Werkzeug ist im Projekt Edge Lab eine **Call-Quelle unter Beobachtung**, kein Kaufsignal:
Regel Edge-First, Paper-only, kein Trading-Code (es gibt keinen). Die Prüfung mit Ursachenanalyse,
Umbau-Plan und Setup für Handy-Alarme steht in `docs/sniper_review.md` (Repo-Root). Änderungen
in Version 0.3.1: Alarm-Records tragen Slot, Kurvenstand, Regelversion und Regel-Hash; `--tape`
schreibt jeden gesehenen Trade eines Tokens mit Alarm mit (Nachrechnen ohne `getTransaction`);
neuer Alarm **↩️ WIDERRUF**, wenn nach einem BLICK ein weiches Warnsignal auftaucht; Telegram
läuft über eine Warteschlange mit Reihenfolge und Wiederholung bei 429; DAS-Holderdaten werden
nur genutzt, wenn sie den Float abdecken (vorher falsche DEV-DUMP/RUG-Alarme durch verzögerte
Indexierung); Holder-Rewards-Coins nutzen den Signer als Creator; das Papier-Trading handelt keine
USDC-Kurven mehr und der Rückblick steigt zum Kurvenstand vor dem Einstieg ein (kein Look-ahead).

Empfohlener Start für frühe Calls aufs Handy (wenig Lärm, Free-Tarif-verträglich), mit
Kontrollgruppe (`--tape-sample 0.1`: jeder zehnte beobachtete Token wird ab dem ersten Trade
mitgeschrieben, auch ohne Alarm):

```bash
python -m holder_scorer live --stufe 1 --tiers go,widerruf,rug,gesperrt --notify go,widerruf,rug --telegram \
  --record live.jsonl --tape live_tape.jsonl --tape-sample 0.1 --budget 1000 --paper papier.jsonl --paper-latency 30
```

Auswertung nach ein paar Tagen, ohne RPC (Umbau P0 aus `docs/sniper_review.md`): Netto-Rendite je
Alarm bei Einstieg 2/10/30/60 s nach dem Alarm und Ausstieg nach 60/300/900 s, mit Kurvengebühr aus
dem Trade, Priority-Fee-Szenario, Token-Account-Einlage, Kontrollgruppe gleichen Alters, Wilson- und
Block-Bootstrap-Intervallen; die Primärzeile (GO, +30 s, +300 s) ist vorab festgelegt:

```bash
python -m holder_scorer tape report live.jsonl live_tape.jsonl            # Text
python -m holder_scorer tape report live.jsonl live_tape.jsonl --json replay.json --priority high
```

**Präzisions-Gate (0.3.2, Modul `profile.py`):** BLICK und GO verlangen zusätzlich, dass in den
letzten 15 s neue Halter (ohne Dev) dazugekommen sind (Stufe 1: ≥ 3, sonst ≥ 2; `--holder-anstieg N`).
Ein GO verlangt außerdem, wenn ein **Profil** geladen ist, dass der Start des Coins den gespeicherten
guten Coins ähnelt: Zum gleichen Checkpoint nach dem ersten Trade (10/20/30/45 s) müssen mindestens
70 % der Merkmale (gewichtet) im Band liegen, das die guten Coins aufgespannt haben (`--profil-min`).
Kopfzeile der Nachricht: `Halter +4/15s · Profil 80 % (MC↑)`. Das kostet null zusätzliche
RPC-Aufrufe: alles entsteht aus den ohnehin abonnierten Log-Trades. Das Profil baust du aus deinen
Aufzeichnungen; Label ist dieselbe Kurvenmathematik wie `tape report` (gut = graduiert oder
Netto-Rendite > 0 bei Einstieg t0+60 s, Ausstieg +180 s), die Checkpoints liegen alle vor dem
Einstieg (kein Look-ahead). `--split 0.5` prüft auf der zeitlich späteren Hälfte, ob die Ähnlichkeit
überhaupt Rendite trennt; ist das Intervall nicht > 0, ist der Filter Lärm und bleibt aus:

```bash
python -m holder_scorer profil bauen --tape live_tape.jsonl --records live.jsonl --papier papier.jsonl --out profil.json
python -m holder_scorer profil zeigen profil.json
python -m holder_scorer live --stufe 1 --tiers go,widerruf,rug,gesperrt --notify go,widerruf,rug --telegram \
  --record live.jsonl --tape live_tape.jsonl --tape-sample 0.1 --budget 1000 --paper papier.jsonl --paper-latency 30 \
  --profil profil.json
```

Liegen noch keine Aufzeichnungen vor, kann eine Mint-Liste (`<Mint> [gut|schlecht]` je Zeile, zum
Beispiel graduierte Coins) die Historie per RPC nachladen: `profil bauen --mints mints.txt --rpc URL
--out profil.json`, begrenzt durch `--max-mints 20` und `--max-pages 10`, Schätzung mit `--dry-run`.
Mindestens 5 gute Coins je Checkpoint, sonst entsteht kein Profil. Ohne Profil gilt nur die
Halter-Anstiegsregel; `--profil-pflicht` unterdrückt GO ganz, bis ein Profil geladen ist.

**Narrativ-Welle und Beobachtungsliste (0.3.3, OQ-028, Entscheidung E-001 in `docs/experte.md`):**
Die früheste Narrativ-Information im eigenen Datenstrom ist die Launch-Welle eines Themas: mehrere
Launches mit demselben Begriff von verschiedenen Devs in wenigen Minuten. Das Themen-Register zählt je
Begriff aus Name, Symbol und Beschreibung die Launches und Devs im 10-Minuten-Fenster gegen die Grundrate
der letzten 6 Stunden und bestimmt den Rang jedes Coins in seiner Welle nach Außen-Zufluss. Gleiche
Social-Link-Ziele mehrerer Launches (derselbe Tweet, derselbe Telegram-Link) erscheinen als `Quelle ×n`.
Das steht als Zeile `Them …` in BLICK und GO und als Feld `narrativ` im Record und im Papier-Kontext,
ohne zusätzliche RPC-Aufrufe und ohne Filterwirkung: Ob Wellen-Erste besser rentieren als Kontrollen,
zeigt erst `tape report` nach genug Alarmen. `--beobachte TIFFANY,…` schickt sofort 👁️ **WATCH**, wenn ein
Launch den Begriff in Name, Symbol oder Beschreibung trägt, unabhängig von `--tiers`/`--notify`. Der
`tape report` zeigt zusätzlich die Latenz Empfang minus Blockzeit der live gesehenen Trades; liegt der
Median über zwei Sekunden, ist jeder Follower-Call strukturell spät. Dazu die Creator-Fee je beobachtetem
Coin als Untergrenze dessen, was ein Launch in seinen ersten Minuten an Gebühr abwirft (OQ-029).

**DexScreener-Bezahlsignale messen (0.3.3, OQ-030, `docs/dexscreener_paid.md`):** Boosts und Enhanced
Token Info („Dex paid") sind öffentliche, bezahlte, zeitgestempelte Ereignisse. `dex beobachten` fragt die
freien Feeds ohne Schlüssel ab (unter 60 bzw. 300 Anfragen je Minute), schreibt jeden Boost-Kauf und jedes
neue Profil mit Preis-Schnappschüssen bei +0/+5/+15/+60 min; `dex report` rechnet die Follower-Rendite je
Horizont mit Wilson und Block-Bootstrap, getrennt nach Boost-Paket, und zeigt, welche eigenen Alarm-Coins
später zahlten. Kein Kauf, keine Boosts; die einzige bekannte Studie misst für geboostete Token im Mittel
−48 Prozent.

```bash
python -m holder_scorer dex beobachten --out dex.jsonl
python -m holder_scorer dex report dex.jsonl --records live.jsonl
```

**Fairness-Gate (0.3.4, OQ-031):** Die Prinzipien eines fairen Launches aus `docs/fair_launch.md` sind
seit 0.3.4 Bedingung für einen Call. Für BLICK und GO: Dev-Anteil aus Kauf und Bestand unter der Stufengrenze
(5/7/10 Prozent), kein Dev-Verkauf, Bundle-Anteil und Zahl fremder Wallets im Create-Fenster begrenzt, keine
Kopie eines Launches der letzten Stunde, kein unsichtbarer Float, keine Bots. Nur für GO zusätzlich: Creator-Historie
geladen und sauber (nicht frisch, keine Serie toter Launches) und Metadaten mit Social-Links und Bild. Unbekannt
zählt nicht als sauber: GO wartet auf Historie und Metadaten. Sagt der Score GO und ein Prinzip ist verletzt, geht
einmal ⛔ GESPERRT in die Aufzeichnung (keine Handy-Nachricht im Standard), nach einem BLICK zusätzlich ↩️ WIDERRUF
mit dem Grund. Jede Nachricht trägt die Zeile `Fair`. `--no-fair` schaltet das Gate aus, `--fair-dev-max`,
`--fair-socials` und `--fair-ohne-historie` stellen es ein. Ob die Sperren richtig waren, zeigt
`tape report --tiers GESPERRT` gegen `--tiers GO`.

**Abstimmung (0.3.5, OQ-032):** Alle Teile verfolgen jetzt dieselben Prinzipien. Der Dev-Faktor des Scores ist
monoton: ein kleiner, gehaltener Dev-Anteil bis 3 Prozent gibt volle Punkte, ab 7 Prozent fällt er, ab 10 Prozent
ist er null, statt wie bisher 6,7 bis 27 Prozent als „aktiven Start" zu belohnen, den das Gate sperrt. ↩️ WIDERRUF
kommt auch nach einem GO, wenn ein schnelles Fairness-Prinzip neu verletzt wird, etwa ein Dev-Verkauf unter der
DEV-RAUS-Schwelle. Die Papier-Strategien kaufen nur noch Coins, die das Gate nicht sperrt (`--paper-ohne-fair` zum
Vergleich). `tape report` enthält die Gate-Prüfung: Rendite der GO-Coins gegen die der GESPERRT-Coins mit
Block-Bootstrap, Lesart „Sperre richtig", „Sperre unnötig" oder „offen". Dafür muss `gesperrt` in `--tiers` stehen,
wie in den Startbefehlen oben. Die Statuszeile zeigt WIDERRUF, GESPERRT, wartende und durch Profil gesperrte GO.

**Launch-Rechner (OQ-029, `docs/fair_launch.md`):** `python -m holder_scorer launch rechner` zeigt aus der
geprüften Kurvenmathematik, welchen Supply-Anteil ein Dev-Kauf ergibt, wie viel Fremdzufluss bis zur Graduation
fehlt, was die Dev-Position dann wert ist, was ein Teilverkauf netto bringt und wie stark er den Kurs drückt,
plus die Creator-Fee bis dahin und die Sniper-Warnungen, die der Plan auslösen würde. Kein Kauf, keine Empfehlung.

```bash
python -m holder_scorer live --stufe 1 --tiers go,widerruf,rug,gesperrt --notify go,widerruf,rug --telegram \
  --record live.jsonl --tape live_tape.jsonl --tape-sample 0.1 --budget 1000 --paper papier.jsonl --paper-latency 30 \
  --beobachte TIFFANY
```

Ehrlicher Hinweis vorab: Das Modul kann keine Zukunft vorhersagen. Es erkennt die
bekannten Muster, mit denen Token scheitern (Bundles, Dev-Dumps, Serien-Deployer,
Bump-Bots, eingeschlafener Handel), und misst, ob gerade organisch neue Käufer
dazukommen. Die Gewichte sind Anfangswerte aus der öffentlichen Forschung, keine
kalibrierten Wahrheiten. Deshalb ist eine Kalibrierung auf deinen eigenen
Beobachtungen eingebaut (siehe unten). Und: Das Modul braucht Handelsdaten, im
Standard 90 Sekunden, im Früh- und Live-Modus 15 bis 20 Sekunden. Ein Kauf im
Erstellungs-Block ist damit prinzipiell nicht vereinbar, das Modul ist ein
Filter für den Einstieg in der zweiten Welle.

## Die Faktoren

| Faktor | Max. Punkte | Was gemessen wird |
|---|---|---|
| Holder-Momentum | 25 | Wachstum der Holder-Zahl in den letzten 60 s aus der Trade-Historie, neue Außen-Käufer pro Minute; Abzug bei Preisanstieg ohne neue Käufer (Self-Pump) |
| Kaufdruck | 15 | Kaufende gegen verkaufende Wallets und Netto-SOL-Fluss der letzten 120 s, nur organische Wallets (ohne Dev, Erstellungs-Block und Bots); Abzug, wenn die Erstkäufer schon verkauft haben oder der Handel stockt |
| Creator-Historie | 15 | Frühere Token des Creators (graduiert, tot, jünger als 30 min), Abstand zum vorigen Launch, Launch-Rate pro Stunde, frische Creator-Wallet |
| Verteilung | 20 | Supply-Anteil, der in den ersten vier Slots gekauft wurde (Bundle), Top-10-Anteil, größter Nicht-Dev-Holder gemessen am bisher verkauften Float, frische oder vom Creator finanzierte frühe Wallets, Überhang der Erstkäufer |
| Dev-Verhalten | 10 | Größe des Dev-Kaufs und Anteil, den der Dev schon verkauft hat |
| Organische Käufe | 5 | Anteil kleiner Außen-Käufe unter 0,1 SOL, Anteil der Käufe von Bump- oder Wash-Wallets |
| Socials | 10 | Echte Twitter-, Telegram- oder Website-Links in den Metadaten (nackte Domains zählen nicht) |

Dazu kommen **K.-o.-Regeln**, die unabhängig von der Punktzahl zu NEIN führen:
Dev hat 90 % oder mehr verkauft, Top-10-Wallets über 60 % des Supplys, größter
Holder über 30 % des Supplys, größter Nicht-Dev-Holder über 60 % des bisher
verkauften Floats, über 35 % des Supplys in den ersten Slots, Serien-Deployer mit
5+ toten Token ohne Graduation, kein Trade seit 60 s ab 90 s Alter oder seit
120 s ab 3 Minuten Alter, mehr als 40 % Wash-Trading-Wallets. Dazu drei
Ausstiegsregeln, die auch einen schon guten Token kippen: ein Bundle ab 5 % des
Supplys hat die Hälfte verkauft, die Erstkäufer haben 70 % ihrer Position
verkauft (ab 5 Außen-Käufern), oder der Kurs liegt 30 % oder mehr unter dem
Hoch der letzten 60 s bei mindestens zwei Verkäufen.

Und **Mindestmengen für JA**: mindestens 12 Außen-Käufer insgesamt, 8
Außen-Käufe in den letzten 120 s und 1 SOL organischer Netto-Zufluss in 120 s.
Ohne diese Mengen bleibt es bei UNKLAR, egal wie gut die Verhältnisse aussehen.
Das verhindert, dass drei bis fünf koordinierte Wallets ein JA erzeugen.

Urteile: Score ab 65 → **JA**, unter 45 → **NEIN**, dazwischen **UNKLAR**.
Token unter 90 s Alter bekommen **ZU_FRUEH**, graduierte Token **GRADUIERT**,
Mayhem- und Nicht-SOL-Kurven immer **UNKLAR** (dafür ist nichts kalibriert).
Alle Schwellen stehen in `ScoringConfig` (`holder_scorer/scoring.py`).

## Installation

Python 3.10 oder neuer. Es wird nur `requests` gebraucht, für den Live-Modus
zusätzlich `websockets`.

```bash
cd tools/holder-scorer
pip install .              # oder: pip install -e .  (zum Weiterentwickeln)
pip install ".[watch]"     # zusätzlich websockets für den Watch-Modus
```

Nach der Installation gibt es den Befehl `holder-scorer`, der überall
funktioniert und dasselbe tut wie `python -m holder_scorer`. Ohne Installation
funktionieren `python -m holder_scorer` und `from holder_scorer import ...` nur,
wenn du das Programm aus dem Ordner `tools/holder-scorer` heraus startest.

Du brauchst eine Solana-RPC-URL. Der kostenlose Helius-Tarif reicht
(https://www.helius.dev) und schaltet die vollständige Holder-Liste (DAS) frei.
Mit einem anderen RPC funktioniert alles, nur die Holder-Zahl kommt dann aus der
Trade-Historie und bei sehr aktiven Token nur aus den 20 größten Konten.

```bash
export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=DEIN_KEY"
```

Der schnellste Start ist das Startskript: es legt eine virtuelle Umgebung
an, installiert das Modul samt `websockets` und startet den Live-Modus mit
Papier-Trading (Stufe 2, Aufzeichnung in `papier.jsonl` und `live.jsonl`,
Telegram für GO und RUG, sobald `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID`
gesetzt sind):

```bash
./start.sh                 # Mac/Linux; Windows: start.bat
STUFE=3 ./start.sh --paper-telegram GO-3x,DEV-HÄLT --narratives trends.txt
```

## Benutzung

```bash
# Ersten Test mit einem echten Token machen (nimm einen 2 bis 5 Minuten alten Token von pump.fun):
python -m holder_scorer selftest <MINT>

# Einen Token bewerten (Kurznachricht mit Kennzahlen und einem Wort als Urteil):
python -m holder_scorer score <MINT>

# Dazu die vollständige Faktor-Tabelle:
python -m holder_scorer score <MINT> --long

# Als JSON, z. B. für einen Bot in einer anderen Sprache (Exit-Code 0 = GO, 1 = sonst, 2 = RPC-Fehler):
python -m holder_scorer score <MINT> --json

# Neue Token live bewerten, jeweils 90 s nach dem Start, und alles aufzeichnen:
python -m holder_scorer watch --record beobachtungen.jsonl

# Früher entscheiden (25 s nach dem Start) und GO-Nachrichten per Telegram schicken:
python -m holder_scorer watch --early --telegram --notify go,rug

# Live-Modus mit Papier-Trading: alle Strategien handeln jeden Call ohne Geld, alles wird aufgezeichnet:
python -m holder_scorer live --stufe 2 --paper papier.jsonl --record live.jsonl
python -m holder_scorer paper report papier.jsonl

# Die Kurzsprache erklären:
python -m holder_scorer legend
```

## Live-Modus: mehr Calls, so früh wie möglich

```bash
python -m holder_scorer live --stufe 2 --telegram --record live.jsonl
```

Der Live-Modus wartet nicht und lädt keine Transaktionen einzeln nach. Er
hört zwei Ströme gleichzeitig:

- **Launches** vom kostenlosen PumpPortal-Stream. Die Create-Nachricht bringt
  Creator, Name, Symbol, Metadaten-Link, den Dev-Kauf und den Kurvenstand mit.
- **Trades** vom Standard-Websocket deines RPC-Anbieters (`logsSubscribe` je
  beobachtetem Token). pump.fun schreibt jeden Trade als `Program data`-Zeile
  in die Logs, die Zeile wird sofort dekodiert. Kein `getTransaction`, keine
  Wartezeit. Helius berechnet Websocket-Daten seit April 2026 mit etwa 20
  Credits je Megabyte, das sind rund 350 Trade-Benachrichtigungen je MB; ein
  Tag Dauerbetrieb kostet damit grob 5.000 bis 10.000 der 1 Mio. Gratis-Credits
  im Monat, die Statuszeile zeigt den Verbrauch. Nur wenn eine Log-Zeile
  ausnahmsweise kein Event enthält oder abgeschnitten wurde, wird die
  Transaktion einmal nachgeladen.

Jeder Token wird nach jedem Trade neu bewertet (höchstens einmal pro Sekunde)
und erzeugt jeden Alarm höchstens einmal je Token:

| Alarm | Wann | Was du damit machst |
|---|---|---|
| 👀 BLICK | erste echte Käufer (nicht Dev, nicht Erstellungs-Block, keine Bots), kein Warnsignal, noch kein volles Urteil; nur in den ersten 60 s | Chart öffnen, selbst entscheiden |
| 🟢 GO | das volle Urteil: Score, Mindestmengen, Zufluss gerade positiv, **keine offene Warnung** (kein Bundle über der Stufengrenze, kein DEV-GROSS, DEV-RAUS, BOTS, FRISCH, FUNDER, SCHNELL, SERIE, UNSICHTBAR), neue Halter in den letzten 15 s und, mit `--profil`, Ähnlichkeit zu den gespeicherten guten Coins; sonst bleibt es bei WARTE | der eigentliche Call |
| 🔴 RUG / ⚫ TOT | ein Token mit BLICK oder GO ist gekippt: Dev-Dump, Bundle raus, Erstkäufer raus, Kurs −30 % vom 60-s-Hoch, MC −35 % seit dem GO, Stillstand | raus |
| ↩️ WIDERRUF | der Call gilt nicht mehr: nach einem BLICK kam ein weiches Warnsignal (DEV-GROSS, SCHNELL, FRISCH, FUNDER, UNSICHTBAR, Bundle über der Grenze …) und ein GO ist nicht mehr zu erwarten; nach einem GO ist ein Fairness-Prinzip verletzt (z. B. der Dev verkauft einen Teil, auch unter der DEV-RAUS-Schwelle) | den Call vergessen |
| ⛔ GESPERRT | der Score sagt GO, aber ein Fairness-Prinzip ist endgültig verletzt (Dev-Anteil, Dev-Verkauf, Bundle-Wallets, Kopie, Historie, Bots, Metadaten) oder das Profil passt nicht; einmal je Token, im Standard nur Aufzeichnung | Lehrmaterial: `tape report --tiers GESPERRT` zeigt später, ob die Sperre richtig war |
| 👁️ WATCH | ein Launch trägt einen Begriff der Beobachtungsliste (`--beobachte`) in Name, Symbol oder Beschreibung; sofort, noch ohne Urteil, einmal je Token | selbst hinsehen, die normalen Alarme folgen |

Ist der Erstellungs-Slot eines Tokens nur geschätzt (der erste Trade kam später
als 1,5 s nach dem Launch an), wartet der Live-Modus bis zu 15 s auf die
nachgeladene Create-Transaktion, bevor er BLICK oder GO schickt, weil sonst
Bundles als echte Käufer durchgehen könnten. Token ohne einen einzigen
Außen-Käufer in 60 s werden verworfen, alle anderen höchstens 240 s beobachtet.

Die Stufe bestimmt, wie viele Calls du bekommst und wie viele davon falsch
sind. Mehr Calls heißt immer auch mehr Fehlalarme, das ist keine
Einstellungsfrage, sondern Mathematik:

| Stufe | BLICK ab | GO ab | Mindestmengen für GO | Bundle-Grenze | Wofür |
|---|---|---|---|---|---|
| 1 vorsichtig | 8 Außen-Käufer, 1,0 SOL Zufluss | 90 s Alter, Score 65 | 12 Käufer, 8 Käufe/120 s, 1,0 SOL | 5 % | wenige, gute Calls |
| 2 Standard | 5 Außen-Käufer, 0,5 SOL | 20 s, Score 65 | 6 Käufer, 5 Käufe, 0,5 SOL | 10 % | ausgewogen |
| 3 aggressiv | 3 Außen-Käufer, 0,25 SOL | 15 s, Score 55 | 4 Käufer, 3 Käufe, 0,3 SOL | 15 % (nur BLICK; GO bleibt bei 10 %) | viele Calls, viele Fehlalarme |

Was das in Nachrichten bedeutet, zeigt eine Simulation mit 400 synthetischen
Launches (Mischung nach der öffentlichen Forschung: 45 % tot, 25 % schwach,
12 % gebündelt, 5 % Dev-Dump, 2 % Wallet-Ring, 11 % organisch oder heiß),
hochgerechnet auf rund 1.000 pump.fun-Launches pro Stunde. Das ist kein
Live-Test, sondern ein Rechenmodell, die echten Zahlen liefert erst `--record`
mit `outcome` und `evaluate`:

| Stufe | BLICK je Stunde | davon organisch/heiß | GO je Stunde | davon organisch/heiß | GO typisch nach |
|---|---|---|---|---|---|
| 1 | ~70 | 85 % | ~20 | 100 % | 90 s |
| 2 | ~80 | 73 % | ~90 | 79 % | 25 s |
| 3 | ~80 | 40 % | ~120 | 69 % | 18 s |

Auch Stufe 1 schickt also gut einen Alarm pro Minute, wenn BLICK an ist. Und
"organisch" heißt nur, dass keine Rug-Mechanik im Spiel war, nicht, dass der
Token gestiegen ist. Auf Stufe 3 gehen Bundles bis 15 % und Wallet-Ringe mit
vier Käufern als BLICK oder GO durch, dafür kommt der Call rund 7 s früher.

Die Hintergrundabfragen per RPC (Creator-Historie, Wallet-Profile, Slot der
Create-Transaktion) starten erst, wenn ein Token mindestens 5 echte Käufer
zeigt (Stufe 1: 8), und nur solange das Stundenbudget reicht: `--budget`
(Standard 4000 Anfrage-Einheiten pro Stunde, also etwa 100.000 Helius-Credits
am Tag, dazu 5.000 bis 10.000 für den Websocket). Ist das Budget aufgebraucht,
laufen Bewertung und Alarme weiter, nur die Warnungen SERIE, SCHNELL, FRISCH
und FUNDER fehlen dann. Mit `--no-side` läuft der Live-Modus ganz ohne
RPC-Last; dann fehlen dieselben Warnungen dauerhaft, und der Erstellungs-Slot
wird nie korrigiert, sodass ein spät gemeldetes Bundle als echte Käufer
durchgehen kann. `--commitment processed` liefert Trades einen Tick früher,
`confirmed` ist sicherer. Mit `--record` landen alle Alarme samt Merkmalen in
der Datei, sodass `outcome` und `evaluate` je Alarmstufe zeigen, wie viele
BLICK- und GO-Token danach wirklich gewachsen sind. Erst damit weißt du, ob
Stufe 3 für dich mehr Treffer bringt oder nur mehr Lärm. Seit 0.3.1 enthält
jeder Record zusätzlich Slot, Kurvenstand (virtuelle/reale Reserven),
Creator, Regelversion und Regel-Hash sowie Datenqualitätsfelder
(`create_slot_known`, `window_guessed`, `trades_seen`, `missing_open`); mit
`--tape DATEI` wird für jeden Token mit Alarm jeder gesehene Trade (Slot,
Reserven, Gebühr) angehängt. Damit lässt sich später jede Einstiegs-Latenz und
jede Regel offline nachrechnen, ohne Transaktionen nachzuladen. `outcome`
markiert seit 0.3.1 Prüfungen lange nach dem Horizont als `stale`.

Die Stellschrauben, wenn dir die Mischung nicht passt:

- `--tiers go,rug,gesperrt --notify go,rug`: nur den eigentlichen Call und den
  Ausstieg schicken, kein BLICK (halbiert die Nachrichten).
- `--stufe 1` oder `--yes-threshold 75`: weniger, dafür bessere GO.
- `--blick-buyers 4 --blick-inflow 0.3`: BLICK auf Stufe 2 etwas früher, ohne
  die GO-Regeln zu lockern.
- `--min-age 30`: GO später, dafür mit mehr Handelsdaten.
- `--commitment processed`: eine Bestätigungsstufe früher, gelegentlich ein
  Trade, den die Kette wieder verwirft.

Zwei Dinge sind bewusst nicht drin: Der PumpPortal-Trade-Stream
(`subscribeTokenTrade`) wäre schneller als jedes RPC, kostet aber 0,01 SOL je
10.000 Trade-Nachrichten und einen API-Key mit Wallet, bei allen Launches also
grob 0,5 SOL am Tag. Und eine Bewertung im Erstellungs-Block gibt es nicht,
weil es dort noch nichts zu bewerten gibt; wer dort kauft, kauft blind.

## Papier-Trading: alle Strategien gleichzeitig, ohne Geld

```bash
# Live-Modus mit Papier-Händler (Aufzeichnung in papier.jsonl):
python -m holder_scorer live --stufe 2 --paper papier.jsonl --record live.jsonl

# Später: Ergebnis je Strategie, mit Was-wäre-wenn auf den aufgezeichneten Preispfaden
python -m holder_scorer paper report papier.jsonl

# Die eingebauten Strategien:
python -m holder_scorer paper strategien

# Frühere Calls nachrechnen (Datei mit "<Mint> <Unix-Zeit oder ISO-Zeit>" je Zeile):
python -m holder_scorer paper rueckblick calls.txt
```

Der Papier-Händler hängt sich an den Live-Modus und handelt jeden Call mit
allen eingebauten Strategien gleichzeitig, mit 0,08 SOL je Trade
(`--paper-size`), ohne dass ein Lamport bewegt wird:

- Kauf und Verkauf werden auf der Bonding Curve gerechnet wie echte:
  Konstantprodukt auf den virtuellen Reserven, 1,25 % pump.fun-Gebühr je
  Seite, eigener Preiseinfluss. Ausgeführt wird 2 s nach der Entscheidung
  (`--paper-latency`) zum Kurvenstand von dann, weil eine echte Transaktion
  erst dann landet. Auch Verkäufe brauchen diese Latenz.
- Jede Sekunde werden die offenen Positionen gegen den aktuellen Kurs
  geprüft: Take-Profit, Stop-Loss, Trailing-Stop, Teilverkauf, Zeitlimit,
  RUG/TOT-Urteil, Dev-Verkauf, Graduation.
- Alles landet in der JSONL-Datei: jeder Kauf mit Auslöser und den Zahlen, auf
  denen er beruhte (Wort, Warnungen, Score, MC, Alter, Außen-Käufer,
  Dev-Verkauf, Bundle, Narrativ), jeder Verkauf mit Grund, Vielfachem,
  Hoch und Tief seit dem Einstieg und Ergebnis, und je Token der Preispfad
  (alle 5 s mit Hoch und Tief dazwischen) bis 15 Minuten nach dem ersten
  Einstieg. Damit lässt sich später jede Regel nachrechnen, die nie gelaufen
  ist.
- Token mit offenen Papier-Positionen bleiben abonniert (höchstens 30 min),
  auch wenn der Live-Modus sie sonst nach 240 s vergessen würde.
- `--paper-telegram GO-3x,DEV-HÄLT` meldet die Papier-Käufe und -Verkäufe
  dieser Strategien kurz per Telegram (zusammen mit `--telegram`).

| Strategie | Einstieg | Ausstieg |
|---|---|---|
| GO-3x | beim GO | Ziel 3x, Stop −40 %, spätestens nach 10 min, bei RUG/TOT |
| GO-2x | beim GO | Ziel 2x, Stop −35 %, 10 min |
| GO-schnell | beim GO | Ziel 1,5x, Stop −25 %, 3 min |
| GO-trail | beim GO | ab 1,5x Trailing-Stop 30 % unter dem Hoch, Stop −40 %, 15 min |
| GO-halb | beim GO | Hälfte bei 2x, Rest mit Trailing-Stop 35 %, Stop −40 % |
| GO-bis-RUG | beim GO | nur bei RUG/TOT, Dev-Verkauf oder nach 15 min (reines Signalfolgen) |
| DEV-HÄLT | beim GO, nur wenn der Dev noch nichts verkauft hat | Ziel 3x, Stop −40 %, sofort raus, wenn der Dev verkauft |
| NARRATIV-GO | beim GO, nur mit Narrativ-Score 60+ | Ziel 3x, Stop −40 % |
| BLICK-3x | schon beim BLICK | Ziel 3x, Stop −50 % |
| BLICK-trail | beim BLICK | ab 1,5x Trailing-Stop 35 %, Stop −50 % |
| NARRATIV-früh | vor jedem Alarm: Narrativ 60+, Dev hält, Bundle ≤ 5 %, ab 2 echten Käufern | Ziel 3x, Stop −50 % |
| SAUBER-früh | vor jedem Alarm: keine Warnung, Dev hält, kein Bundle, ab 3 echten Käufern | Ziel 2x, Stop −40 %, 5 min |

Mit `--paper-strategies GO-3x,DEV-HÄLT` läuft nur ein Teil; eigene Varianten
sind eine Zeile in `STRATEGIES` (`holder_scorer/paper.py`).

**Narrativ.** Ein Narrativ lässt sich nicht messen, nur seine Spuren: echte
Social-Links (je 15 Punkte, bis drei), eine Beschreibung und ein Bild in den
Metadaten (10 und 5), ein Treffer in deiner Trend-Liste (`--narratives
trends.txt`, ein Wort je Zeile, 25 Punkte), abzüglich Wegwerf-Namen (−20) und
Kopien: derselbe Name oder dasselbe Symbol wie ein Launch der letzten Stunde
(−30). Grundwert 30, Skala 0 bis 100. Die Trend-Liste musst du pflegen, das
Modul kennt keine Nachrichten.

**Der Report.** `paper report` zeigt je Strategie die Zahl der Trades, die
Trefferquote, Mittel und Median des Ergebnisses je Trade, die Summe in SOL,
ein 95 %-Konfidenzintervall des Mittelwerts (Bootstrap), den größten
Rückschlag der Summe, die Ausstiegsgründe und den Endstand, wenn du mit
0,25 SOL Kasse (`--kasse`) nur so viele Positionen offen halten kannst, wie
das Geld hergibt. Als Kandidat gilt eine Strategie erst, wenn die untere Grenze
des Intervalls über 0 liegt; vorher steht dort, wie viele Trades bei gleichem
Mittelwert grob nötig wären. Dazu rechnet er auf den aufgezeichneten Pfaden
64 Regeln durch (Ziel 1,5x bis 5x, Stop −25 % bis keiner, 2 bis 15 min) und
nennt die beste, samt der Gegenprobe: die beste Regel der ersten Hälfte der
Trades und was sie in der zweiten Hälfte gebracht hätte. Wer 64 Regeln auf 30
Trades probiert, findet immer eine, die gut aussieht; die zweite Hälfte zeigt,
ob sie hält.

**Rückblick auf frühere Calls.** `paper rueckblick calls.txt` lädt für jeden
Call die Trades des Tokens aus der Kette (bis 15 min nach dem Call), setzt den
Einstieg 2 s nach dem Call und zeigt Hoch danach, Anteil der Calls mit 2x und
3x und die Ergebnisse der Regeln. Das kostet je Token bis zu einigen tausend
getTransaction-Anfragen, bei Helius also Kontingent; für 20 bis 50 Calls ist
das noch in Ordnung.

**Was über solche Calls schon bekannt ist** (Stand September 2026, aus
öffentlichen Auswertungen; Quellen in der Recherche zum Projekt):

- Ein Call-Kanal mit 4.356 Calls: Median-Hoch nach dem Call 1,64x, 36 bis
  39 % erreichen 2x. Das sind Höchststände, keine realisierten Gewinne; wer
  ein 3x-Ziel wartet, verpasst die meisten davon.
- Eine systematische Prüfung von 266 Einstiegsvarianten auf 63.000
  unselektierten Launches (6,3 Mio. Trades): keine einzige mit einer unteren
  Konfidenzgrenze über 0; jeder Einstieg, der auf sichtbare Käufer wartet
  (Tempo, Breite, Kaufdruck, Dip, KOL-Folgen), verliert nach Gebühren. Die
  Latenz zwischen Signal und Kauf kostet 5 bis 16 Prozentpunkte je Trade.
  Filter gegen Bundles, Konzentration und Wallet-Ringe machen die Verluste 2
  bis 11 Punkte kleiner, erzeugen aber keinen Gewinn.
- Ein Kurventrade kostet 1,25 % je Seite, dazu der eigene Preiseinfluss:
  ein Hin und Zurück ohne Kursbewegung verliert etwa 2,5 bis 3 %.

Das heißt nicht, dass es keine Strategie geben kann. Es heißt, dass die
Beweislast bei der Strategie liegt: erst wenn der Papier-Report über einige
hundert Trades eine untere Konfidenzgrenze über 0 zeigt, ist ein Versuch mit
echtem Geld mehr als Raten, und selbst dann wird es real schlechter
(fehlgeschlagene Transaktionen, Priority-Fees, Slippage bei dünnen Kurven).

## Die Kurznachricht

Jede Bewertung ist zehn kurze Zeilen: ein Wort als Urteil, die Kennzahlen
untereinander, die Warnungen als letzte Zeile. Beispiel für einen guten Token:

```
🟢 GO 82 · PEPE2 · 1m32s
MC   38k$ · 12.1 SOL
Vol  9.4k$ · V/MC 0.25 · 60s 2.1 SOL
Liq  8.7 SOL · L/MC 0.72 · Kurve 32%
Hold 48 · +27 in 60s
Buys 41 / 4 · Netto +3.2 SOL
Dev  1.8% hält · Bundle 2%
Crea 3 Tok · 1 grad · 2 tot
Soc  2 Links · Bots 0%
⚠️   –
```

Und für einen offensichtlichen Rug, wie ihn ein Sniper trotzdem kauft:

```
🔴 RUG · SCAM · 3m20s
MC   900k$ · 6000.0 SOL
Vol  5.0k$ · V/MC 0.006
Liq  33.3 SOL · L/MC 0.006
Hold 61
Buys 40 / 22
Dev  ?
Crea ?
Soc  keine
⚠️   FAKE-MC 0.006 · DÜNN 0.006
```

Die Wörter:

| Wort | Bedeutung |
|---|---|
| 🟢 GO | kein Warnsignal, genug echte Käufer, gerade Zulauf |
| 🟡 WARTE | unklar, oder der Score reicht, aber die Mindestmengen fehlen |
| ⏳ FRÜH | zu jung für ein Urteil |
| ⚪ NEIN | schwach, aber kein Rug-Muster |
| 🔴 RUG | Rug-Muster: Bundle, Dev-Dump, Serien-Deployer, Konzentration, Fake-MC oder dünne Liquidität |
| ⚫ TOT | Handel eingeschlafen |
| 🎓 GRAD | graduiert, handelt auf PumpSwap: nur Marktzahlen |
| ❔ ? | keine Daten oder RPC-Fehler |

Die wichtigsten Warnungen: `BUNDLE 30%/12%` (gekauft/gehalten in den ersten
Slots), `DEV-DUMP`, `DEV-RAUS 40%`, `SERIE 12/0/11` (frühere Token /
graduiert / tot), `SCHNELL` (Creator startet im Minutentakt), `FRISCH 5/6`
(frische frühe Wallets), `FUNDER 4` (vom Creator finanziert), `TOP1 35%`,
`TOP10 61%`, `BOTS 40%`, `WASH`, `SELF-PUMP`, `EXIT 62%` (Erstkäufer raus),
`DUMP −35%` (Kurs unter dem Hoch der letzten 60 s), `UNSICHTBAR 18%` (Supply, das die Kurve
verlassen hat, ohne dass ein gesehener Trade es erklärt: Käufe vor dem
Zuhören), `FAKE-MC 0.006` (Volumen der letzten Stunde geteilt durch MC),
`DÜNN 0.006` (Liquidität geteilt durch MC), `STILL 95s`, `NOSOC`, `LÜCKE`
(Daten unvollständig), `MINDEST` (Score reicht, Mindestmengen fehlen). Die
ganze Liste zeigt `python -m holder_scorer legend`.

Die Marktzahlen (MC in USD, Volumen der letzten Stunde, Liquidität,
Käufe/Verkäufe) kommen von DexScreener, kostenlos und ohne Schlüssel, und
funktionieren auch für graduierte Token, die das On-Chain-Modul nicht mehr
lesen kann. Auf der Kurve werden MC, Volumen und Liquidität direkt aus der
Chain berechnet; der SOL-Kurs kommt aus dem DexScreener-Paar, sonst von
CoinGecko, sonst aus der Umgebungsvariable `SOL_USD`.

**Telegram:** Einen Bot bei @BotFather anlegen, den Token in
`TELEGRAM_BOT_TOKEN` und deine Chat-ID in `TELEGRAM_CHAT_ID` setzen. `score
--telegram` schickt die Kurznachricht, `watch --telegram` schickt sie für die
Urteile aus `--notify` (Standard: nur GO).

**Früh-Modus (`--early`):** Urteil ab 20 s Alter statt 90 s, mit kleineren
Mindestmengen (6 Außen-Käufer, 5 Außen-Käufe, 0,5 SOL Zufluss) und strengeren
Stillstandsregeln, dazu weniger Abfragen (150 Transaktionen, 4 Wallet-Profile,
40 Creator-Transaktionen). Im Watch-Modus wird dann 25 s nach dem Start
bewertet. Früher heißt weniger Beweise: mehr WARTE und mehr falsche GO als
bei 90 s. Wie viel mehr, sagt dir `evaluate` nach ein paar Stunden Aufzeichnung.

Beispielausgabe von `score --long` (die Faktor-Tabelle unter der Kurznachricht):

```
Token 7xKX...pump
Alter 142 s | Trades 63 | Holder 48 (das) | Kurve 18.2 % | Quote SOL: ja

  Holder-Momentum     25.0 / 25   Holder 21 → 48 in 60 s (+129 %), 24 neue Käufer
  Kaufdruck           15.0 / 15   31 kaufende / 3 verkaufende Wallets in 120 s (41 Käufe / 4 Verkäufe, ohne Dev, Bundle und Bots)
  Creator-Historie    10.9 / 15   3 frühere Token: 1 graduiert, 2 tot, 0 jünger als 30 min
  Verteilung          16.4 / 20   Bundle-Anteil 2.1 % (2 Wallets), Top-10 23.9 %, größter Nicht-Dev-Holder 9.8 % des Floats
  Dev-Verhalten        7.0 / 10   Dev-Kauf 1.8 %  [Dev hält noch alles (1.8 % des Supplys)]
  Organische Käufe     5.0 / 5    71.4 % der Außen-Käufe unter 0,1 SOL, Median 0.045 SOL
  Socials             10.0 / 10   2 Social-Links

Score 89 / 100  →  JA

(9.4 s, 131 Request-Einheiten in 21 HTTP-Aufrufen, 0 Wiederholungen (getTransaction 112, getSignaturesForAddress 9, ...))
```

## Kosten und Dauer

Jede Transaktion der Token-Historie wird einzeln geladen, auch innerhalb eines
Batches, und Helius zählt jede davon als Anfrage. Ein typischer 90 Sekunden alter
Token mit 80 Trades kostet rund 100 bis 160 Anfrage-Einheiten, ein sehr aktiver
Token bis zu etwa 450 (Obergrenze `max_tx=400`). Bei 10 Anfragen pro Sekunde sind
das etwa 8 bis 20 Sekunden, weil die unabhängigen Abfragen (Holder, Creator,
frühe Wallets, Metadaten) parallel laufen. `--no-deep` spart die Profile der
frühen Wallets, etwa 15 Einheiten. Creator- und Wallet-Profile werden für 30
Minuten zwischengespeichert, im Watch-Modus kostet ein wiederkehrender Creator
also nichts mehr.

Ein rund um die Uhr laufender Watch-Modus würde das kostenlose Helius-Kontingent
von einer Million Credits im Monat innerhalb weniger Tage aufbrauchen. Deshalb
bewertet er nur pump.fun-Launches, überspringt Token, die er nicht innerhalb von
`--max-lag` Sekunden nach der Fälligkeit bewerten kann, prüft vorab mit einer
einzigen Anfrage, ob ein Token überhaupt `--min-trades` Transaktionen hat, und
lässt sich mit `--max-per-hour` auf eine feste Zahl Launches pro Stunde
begrenzen. Was übersprungen wurde, steht in der Statistikzeile; mit `--record`
landen auch die vom Vorfilter abgewiesenen Token als Zeile mit dem Urteil
VORFILTER in der Datei, damit `outcome` und `evaluate` zeigen, ob der Vorfilter
etwas Gutes wegwirft.

## In einen Bot einbauen

**Python-Bot** (z. B. der Chainstack pump.fun-Bot oder ein eigener): einen
RPC-Client einmal anlegen, vor dem Kauf aufrufen und nur bei `report.buy_signal`
kaufen.

```python
from holder_scorer import quick_check, format_short, send_telegram, make_rpc, ScoringConfig

rpc = make_rpc(RPC_URL)                       # einmal anlegen: Rate-Limit und Cache bleiben erhalten
cfg = ScoringConfig.early()                   # oder ScoringConfig() für die 90-Sekunden-Variante

def darf_kaufen(mint: str) -> bool:
    report = quick_check(mint, rpc, config=cfg)
    text = format_short(report)               # zehn Zeilen, ein Wort als Urteil
    print(text)
    if report.word in ("GO", "RUG"):
        send_telegram(text)                   # nutzt TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID
    return report.buy_signal                  # True nur bei GO
```

`quick_check` wirft `RpcError`, wenn der Endpunkt die Pflichtabfragen (Kurve,
Signaturliste) nicht beantwortet; alles andere wird als "unbekannt" gewertet und
in `report.notes` erklärt. `evaluate_token` liefert weiterhin nur das
On-Chain-Urteil mit der Faktor-Tabelle.

**Bot in einer anderen Sprache** (TypeScript, Rust, …): das Kommando
`python -m holder_scorer score <MINT> --json` als Unterprozess starten und das
JSON lesen. Feld `word` ist das Urteil, `flags` die Warnungen, `mc_usd`,
`volume_usd`, `turnover`, `liquidity_sol`, `holders`, `buys`, `sells`,
`dev_share`, `bundle_share` die Kennzahlen, `verdict.features` alle Rohwerte.

**Fertiger Bot oder Terminal ohne Quellcode** (Telegram-Bots, GMGN, Axiom, …):
den Watch-Modus daneben laufen lassen und nur Token kaufen, die mit JA
zurückkommen. Das ist langsamer als der Bot selbst, was bei diesem Ansatz auch so
gewollt ist: Das Modul bewertet erst, wenn es Daten gibt.

## Kalibrieren: Welche Faktoren stimmen wirklich?

Die Gewichte sind Annahmen. Ob sie im aktuellen Markt stimmen, zeigt nur die
Nachprüfung an echten Token. Der Ablauf:

```bash
# 1. Ein paar Stunden aufzeichnen (kein Kauf nötig; das Kontingent im Blick behalten):
python -m holder_scorer watch --delay 90 --record beobachtungen.jsonl

# 2. Später nachschauen, ob die Holder gewachsen sind (Standard: 15 Minuten, Faktor 1,5):
python -m holder_scorer outcome --file beobachtungen.jsonl

# 3. Auswerten:
python -m holder_scorer evaluate --file beobachtungen.jsonl
```

Die Datei wird nur angehängt, nie umgeschrieben: `outcome` darf laufen, während
`watch --record` weiter schreibt, und ein Abbruch verliert nichts. Die
Nachprüfung kostet mit Helius zwei Anfragen je Token. `evaluate` zeigt die
Trefferquote je Urteil, für jeden Faktor den Anteil gewachsener Token im
niedrigen, mittleren und hohen Drittel, und ab 30 vollständigen Aufzeichnungen
eine logistische Regression. Faktoren, die im hohen Drittel keine bessere Quote
haben als im niedrigen, kannst du in `ScoringConfig` auf ein kleines Gewicht
setzen. Erst mit dieser Auswertung weißt du, ob das Modul in deinem Markt besser
ist als Raten.

## Was das Modul nicht kann

- Es sieht nur die Bonding-Curve-Phase. Nach der Graduation auf PumpSwap gilt
  ein anderes Programm, das Urteil lautet dann GRADUIERT.
- Token-Transfers außerhalb von Käufen und Verkäufen werden in der
  Holder-Historie nicht erfasst. Das Momentum wird deshalb bewusst nur aus der
  Trade-Historie berechnet; die aktuelle Holder-Zahl kommt über Helius DAS
  trotzdem vollständig.
- Sniper rotieren Wallets und bündeln Käufe über viele Adressen. Das Modul
  erkennt Bundles in den ersten Slots, frische oder vom Creator finanzierte
  Wallets und Wallets mit immer gleicher Kaufgröße, aber nicht jede
  Verschleierung.
- Die Creator-Historie stammt aus den letzten 80 Transaktionen der
  Creator-Wallet (einstellbar über `creator_scan_tx`). Eine Suche über Helius
  DAS gibt es nicht, weil DAS pump.fun-Token nicht nach Creator indiziert. Bei
  sehr aktiven Creators ist das nur ein Ausschnitt, und Wallet-Rotation umgeht
  die Prüfung ganz.
- Sehr heiße Token mit mehr als 400 erfolgreichen Transaktionen werden nur
  teilweise geladen (die ersten 60 und die letzten 150 Sekunden). Bundle- und
  Dev-Werte bleiben dann erhalten, die Holder-Historie wird als unbekannt
  behandelt.
- Der Live-Modus sieht nur Trades ab dem Moment, in dem er einen Token
  abonniert hat. Was davor lief (etwa Käufe im selben Block wie der Launch,
  deren Log-Nachricht nie ankam), erkennt er nur an der Lücke zwischen
  Kurvenstand und gesehenen Käufen (Warnung UNSICHTBAR) und über die
  nachgeladene Create-Transaktion. Ist der Erstellungs-Slot nur geschätzt,
  hält er BLICK und GO bis zu 15 s zurück.
- Ein Urteil JA ist keine Kaufempfehlung, sondern "kein bekanntes Warnsignal,
  genug echte Käufer und gerade Zulauf". Wie viele JA-Token danach wirklich
  wachsen, sagt dir erst `evaluate`.

## Entwicklung

```bash
pip install pytest
python -m pytest -q
```

Die Tests prüfen Base58 und die Adressableitung (bei installiertem `solders`
gegen die Referenz), die Decoder für Trade-, Create-Events und
Bonding-Curve-Konten nach der offiziellen IDL, die RPC-Schicht gegen einen
HTTP-Stub (Batches, Fehlercodes, DAS-Erkennung, Rate-Limit über mehrere
Threads), die Datensammlung gegen einen RPC-Stub, die Kalibrierdatei, fünf
Bewertungsszenarien (organisches Wachstum, gebündelter Dev-Dump, toter Token,
zu junger Token, koordinierter Wallet-Ring), die Live-Engine und den
Papier-Händler (Kurven-Mathematik, Einstiege je Strategie, alle
Ausstiegsgründe, Preispfade, Report, Rückblick gegen einen Historien-Stub).
Die Programm-Layouts stammen aus https://github.com/pump-fun/pump-public-docs
(Stand September 2026).
