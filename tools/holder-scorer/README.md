# holder-scorer: Bekommt dieser Coin mehr Holder?

Ein Bewertungsmodul für pump.fun-Token auf Solana. Es sammelt On-Chain-Daten zu
einem Token, berechnet daraus mehrere Faktoren und gibt ein Urteil ab: **JA**
(wahrscheinlich mehr Holder), **UNKLAR** oder **NEIN**. Gedacht als Filter, der
vor dem Kauf in einen Sniper- oder Copy-Trading-Bot eingehängt wird, oder als
Werkzeug, das neben einem fertigen Bot mitläuft.

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
verkauft (ab 5 Außen-Käufern), oder der Kurs ist in 60 s um 30 % oder mehr
gefallen bei mindestens zwei Verkäufen.

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
und erzeugt höchstens drei Alarme:

| Alarm | Wann | Was du damit machst |
|---|---|---|
| 👀 BLICK | erste echte Käufer (nicht Dev, nicht Erstellungs-Block, keine Bots), kein Warnsignal, noch kein volles Urteil; nur in den ersten 60 s | Chart öffnen, selbst entscheiden |
| 🟢 GO | das volle Urteil: Score, Mindestmengen, Zufluss gerade positiv und **keine offene Warnung** (kein Bundle über der Stufengrenze, kein DEV-GROSS, DEV-RAUS, BOTS, FRISCH, FUNDER, SCHNELL, SERIE, UNSICHTBAR); sonst bleibt es bei WARTE | der eigentliche Call |
| 🔴 RUG / ⚫ TOT | ein Token mit BLICK oder GO ist gekippt: Dev-Dump, Bundle raus, Erstkäufer raus, Kurs −30 % in 60 s, MC −35 % seit dem GO, Stillstand | raus |

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
| 3 aggressiv | 3 Außen-Käufer, 0,25 SOL | 15 s, Score 55 | 4 Käufer, 3 Käufe, 0,3 SOL | 15 % | viele Calls, viele Fehlalarme |

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
Stufe 3 für dich mehr Treffer bringt oder nur mehr Lärm.

Die Stellschrauben, wenn dir die Mischung nicht passt:

- `--tiers go,rug` oder `--notify go,rug`: nur den eigentlichen Call und den
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
`DUMP 35%` (Kurs in 60 s gefallen), `UNSICHTBAR 18%` (Supply, das die Kurve
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
Threads), die Datensammlung gegen einen RPC-Stub, die Kalibrierdatei und fünf
Bewertungsszenarien (organisches Wachstum, gebündelter Dev-Dump, toter Token,
zu junger Token, koordinierter Wallet-Ring). Die Programm-Layouts stammen aus
https://github.com/pump-fun/pump-public-docs (Stand September 2026).
