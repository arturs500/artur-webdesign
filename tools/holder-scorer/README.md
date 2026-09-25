# holder-scorer: Bekommt dieser Coin mehr Holder?

Ein Bewertungsmodul für pump.fun-Token auf Solana. Es sammelt On-Chain-Daten zu
einem Token, berechnet daraus mehrere Faktoren und gibt ein Urteil ab: **JA**
(wahrscheinlich mehr Holder), **UNKLAR** oder **NEIN**. Gedacht als Filter, der
vor dem Kauf in einen Sniper- oder Copy-Trading-Bot eingehängt wird, oder als
Werkzeug, das neben einem fertigen Bot mitläuft.

Ehrlicher Hinweis vorab: Das Modul kann keine Zukunft vorhersagen. Es erkennt die
bekannten Muster, mit denen Token scheitern (Bundles, Dev-Dumps, Serien-Deployer,
eingeschlafener Handel), und misst, ob gerade organisch neue Käufer dazukommen.
Die Gewichte sind Anfangswerte aus der öffentlichen Forschung, keine kalibrierten
Wahrheiten. Deshalb ist eine Kalibrierung auf deinen eigenen Beobachtungen
eingebaut (siehe unten). Und: Das Modul braucht 45 bis 120 Sekunden Handelsdaten.
Ein Kauf im Erstellungs-Block ist damit prinzipiell nicht vereinbar, das Modul ist
ein Filter für den Einstieg in der zweiten Welle.

## Die Faktoren

| Faktor | Max. Punkte | Was gemessen wird |
|---|---|---|
| Holder-Momentum | 25 | Wachstum der Holder-Zahl in den letzten 60 s, neue Käufer pro Minute |
| Kaufdruck | 15 | Verhältnis Käufe zu Verkäufen und Netto-SOL-Fluss der letzten 120 s |
| Creator-Historie | 20 | Frühere Token des Creators: wie viele graduiert, wie viele tot; frische Creator-Wallet |
| Verteilung | 20 | Supply-Anteil, der im Erstellungs-Block gekauft wurde (Bundle), Top-10-Anteil, frische oder vom Creator finanzierte frühe Wallets |
| Dev-Verhalten | 10 | Größe des Dev-Kaufs und ob der Dev schon verkauft hat |
| Organische Käufe | 5 | Anteil kleiner Käufe unter 0,1 SOL, Median-Kaufgröße |
| Socials | 5 | Echte Twitter-, Telegram- oder Website-Links in den Metadaten |

Dazu kommen **K.-o.-Regeln**, die unabhängig von der Punktzahl zu NEIN führen:
Dev hat 90 % oder mehr verkauft, Top-10-Wallets über 60 %, größter Holder über
30 %, über 35 % des Supplys im Erstellungs-Block, Serien-Deployer mit 5+ toten
Token ohne Graduation, kein Trade seit 120 s bei über 3 Minuten Alter, mehr als
40 % Wash-Trading-Wallets.

Urteile: Score ab 65 → **JA**, unter 45 → **NEIN**, dazwischen **UNKLAR**.
Token unter 45 s Alter bekommen **ZU_FRUEH**, graduierte Token **GRADUIERT**.
Alle Schwellen stehen in `ScoringConfig` (`holder_scorer/scoring.py`).

## Installation

Python 3.10 oder neuer. Es wird nur `requests` gebraucht, für den Live-Modus
zusätzlich `websockets`.

```bash
cd tools/holder-scorer
pip install -r requirements.txt
pip install websockets     # nur für den Watch-Modus
```

Du brauchst eine Solana-RPC-URL. Der kostenlose Helius-Tarif reicht
(https://www.helius.dev, 1 Mio. Credits pro Monat, 10 Anfragen pro Sekunde) und
schaltet die schnelleren Holder- und Creator-Abfragen (DAS) frei. Mit einem
anderen RPC funktioniert alles, nur die Holder-Liste ist dann auf die 20 größten
Konten begrenzt und die Creator-Suche langsamer.

```bash
export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=DEIN_KEY"
```

## Benutzung

```bash
# Ersten Test mit einem echten Token machen (nimm einen 1 bis 5 Minuten alten Token von pump.fun):
python -m holder_scorer selftest <MINT>

# Einen Token bewerten:
python -m holder_scorer score <MINT>

# Als JSON, z. B. für einen Bot in einer anderen Sprache (Exit-Code 0 = JA, 1 = sonst, 2 = Fehler):
python -m holder_scorer score <MINT> --json

# Neue Token live bewerten, jeweils 60 s nach dem Start, und alles aufzeichnen:
python -m holder_scorer watch --delay 60 --record beobachtungen.jsonl
```

Beispielausgabe von `score`:

```
Token 7xKX...pump
Alter 142 s | Trades 63 | Holder 48 (das) | Kurve 18.2 % | Quelle SOL: ja

  Holder-Momentum     25.0 / 25   Holder 21 → 48 in 60 s (+129 %)
  Kaufdruck           15.0 / 15   41 Käufe / 4 Verkäufe in 120 s
  Creator-Historie    14.6 / 20   3 frühere Token, 1 graduiert, 2 tot
  Verteilung          16.4 / 20   Bundle-Anteil 2.1 % (2 Wallets), Top-10 23.9 %
  Dev-Verhalten       10.0 / 10   Dev-Kauf 1.8 %  [Dev hält noch alles]
  Organische Käufe     5.0 / 5    71.4 % der Käufe unter 0,1 SOL, Median 0.045 SOL
  Socials              5.0 / 5    2 Social-Links

Score 91 / 100  →  JA
```

## In einen Bot einbauen

**Python-Bot** (z. B. der Chainstack pump.fun-Bot oder ein eigener): vor dem Kauf
aufrufen und nur bei `verdict.buy_signal` kaufen.

```python
from holder_scorer import evaluate_token, ScoringConfig

cfg = ScoringConfig(min_age_s=45, yes_threshold=65)

def darf_kaufen(mint: str) -> bool:
    verdict = evaluate_token(mint, rpc_url=RPC_URL, config=cfg)
    print(verdict.label, round(verdict.score), verdict.hard_fails)
    return verdict.buy_signal
```

`evaluate_token` braucht je nach RPC 2 bis 8 Sekunden (15 bis 40 RPC-Aufrufe).
Mit `deep=False` entfällt die Prüfung der frühen Wallets, das spart etwa die Hälfte.

**Bot in einer anderen Sprache** (TypeScript, Rust, …): das Kommando
`python -m holder_scorer score <MINT> --json` als Unterprozess starten und das
JSON lesen. Feld `label` ist das Urteil, `score` die Punktzahl, `hard_fails` die
K.-o.-Gründe, `features` alle Rohwerte.

**Fertiger Bot oder Terminal ohne Quellcode** (Telegram-Bots, GMGN, Axiom, …):
den Watch-Modus daneben laufen lassen und nur Token kaufen, die mit JA
zurückkommen. Das ist langsamer als der Bot selbst, was bei diesem Ansatz auch so
gewollt ist: Das Modul bewertet erst, wenn es Daten gibt.

## Kalibrieren: Welche Faktoren stimmen wirklich?

Die Gewichte sind Annahmen. Ob sie im aktuellen Markt stimmen, zeigt nur die
Nachprüfung an echten Token. Der Ablauf:

```bash
# 1. Mehrere Stunden oder Tage aufzeichnen (kein Kauf nötig):
python -m holder_scorer watch --delay 60 --record beobachtungen.jsonl

# 2. Später nachschauen, ob die Holder gewachsen sind (Standard: 15 Minuten, Faktor 1,5):
python -m holder_scorer outcome --file beobachtungen.jsonl

# 3. Auswerten:
python -m holder_scorer evaluate --file beobachtungen.jsonl
```

`evaluate` zeigt die Trefferquote je Urteil, für jeden Faktor den Anteil
gewachsener Token im niedrigen, mittleren und hohen Drittel, und ab 30
vollständigen Aufzeichnungen eine logistische Regression. Faktoren, die im
hohen Drittel keine bessere Quote haben als im niedrigen, kannst du in
`ScoringConfig` auf ein kleines Gewicht setzen. Erst mit dieser Auswertung
weißt du, ob das Modul in deinem Markt besser ist als Raten.

## Was das Modul nicht kann

- Es sieht nur die Bonding-Curve-Phase. Nach der Graduation auf PumpSwap gilt
  ein anderes Programm, das Urteil lautet dann GRADUIERT.
- Token-Transfers außerhalb von Käufen und Verkäufen werden in der
  Holder-Historie nicht erfasst. Die aktuelle Holder-Zahl kommt über Helius
  DAS trotzdem vollständig.
- Sniper rotieren Wallets und bündeln Käufe über viele Adressen. Das Modul
  erkennt Bundles im Erstellungs-Block und frische, vom Creator finanzierte
  Wallets, aber nicht jede Verschleierung.
- Die Creator-Historie ist bei Creators mit sehr vielen Transaktionen nur ein
  Ausschnitt (Standard: die letzten 120 Transaktionen plus DAS-Suche).
- Ein Urteil JA ist keine Kaufempfehlung, sondern "kein bekanntes Warnsignal und
  gerade Zulauf". Wie viele JA-Token danach wirklich wachsen, sagt dir erst
  `evaluate`.

## Entwicklung

```bash
pip install pytest
python -m pytest -q
```

Die Tests prüfen Base58 und die Adressableitung (bei installiertem `solders`
gegen die Referenz), die Decoder für Trade-, Create-Events und
Bonding-Curve-Konten nach der offiziellen IDL sowie vier Bewertungsszenarien
(organisches Wachstum, gebündelter Dev-Dump, toter Token, zu junger Token).
Die Programm-Layouts stammen aus https://github.com/pump-fun/pump-public-docs
(Stand September 2026).
