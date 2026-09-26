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
Beobachtungen eingebaut (siehe unten). Und: Das Modul braucht mindestens 90
Sekunden Handelsdaten. Ein Kauf im Erstellungs-Block ist damit prinzipiell nicht
vereinbar, das Modul ist ein Filter für den Einstieg in der zweiten Welle.

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
120 s ab 3 Minuten Alter, mehr als 40 % Wash-Trading-Wallets.

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

# Einen Token bewerten:
python -m holder_scorer score <MINT>

# Als JSON, z. B. für einen Bot in einer anderen Sprache (Exit-Code 0 = JA, 1 = sonst, 2 = RPC-Fehler):
python -m holder_scorer score <MINT> --json

# Neue Token live bewerten, jeweils 90 s nach dem Start, und alles aufzeichnen:
python -m holder_scorer watch --delay 90 --record beobachtungen.jsonl
```

Beispielausgabe von `score`:

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
RPC-Client einmal anlegen, vor dem Kauf aufrufen und nur bei `verdict.buy_signal`
kaufen.

```python
from holder_scorer import evaluate_token, make_rpc, ScoringConfig

rpc = make_rpc(RPC_URL)                       # einmal anlegen: Rate-Limit und Cache bleiben erhalten
cfg = ScoringConfig(min_age_s=90, yes_threshold=65)

def darf_kaufen(mint: str) -> bool:
    verdict = evaluate_token(mint, rpc=rpc, config=cfg)
    print(verdict.label, round(verdict.score), verdict.hard_fails, verdict.notes)
    return verdict.buy_signal
```

`evaluate_token` wirft `RpcError`, wenn der Endpunkt die Pflichtabfragen (Kurve,
Signaturliste) nicht beantwortet; alles andere wird als "unbekannt" gewertet und
in `verdict.notes` erklärt.

**Bot in einer anderen Sprache** (TypeScript, Rust, …): das Kommando
`python -m holder_scorer score <MINT> --json` als Unterprozess starten und das
JSON lesen. Feld `label` ist das Urteil, `score` die Punktzahl, `hard_fails` die
K.-o.-Gründe, `notes` die Einschränkungen, `features` alle Rohwerte.

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
