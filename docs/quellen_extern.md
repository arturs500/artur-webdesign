# Außenquellen (Sniper 0.3.6, OQ-033) – Informationen nicht nur aus dem eigenen Papier-Test

Stand 2026-10-04. Nutzerauftrag: „Informationen nicht nur aus unserem Paper-Trade-Test holen, sondern auch woanders."
Entscheidung des Experten (E-013): drei kostenlose, schlüssellose Quellen record-only anbinden, kein Gate, keine neuen
RPC-Aufrufe im Live-Betrieb. Alle Anbieter-Hosts waren in der Arbeitsumgebung gesperrt (pumpportal.fun,
api.dexscreener.com, api.rugcheck.xyz, api.geckoterminal.com, apiguide.geckoterminal.com): Belege sind **[Snippet]**
oder **NICHT VERIFIZIERT**, der Code liest Antworten tolerant und hebt Rohdaten auf; die erste Live-Minute auf dem
Rechner des Nutzers ist die Verifikation (Abschnitt 5).

## 1. Blinde Flecken bis 0.3.5

| Fleck | Folge | Was 0.3.6 dagegen tut |
|---|---|---|
| Referenz-Coins nur aus Tape/Records/Papier, also nur Coins, die der Sniper selbst gerufen oder gesampelt hat | gute Coins, die er verpasst hat, fehlen im Profil; das Profil bestätigt den eigenen Blickwinkel | `profil bauen --extern`: graduierte Coins der ganzen Plattform als gute Referenz |
| Labels nur aus den ersten 300 s der Kurve; Graduation zählt im Replay als Verlust (Position 0) | ob ein GO später graduiert, nach einem Tag lebt oder sofort stirbt, ist unbekannt | Migrationsfeed (exakte Graduation) und Nachlauf nach 1 h/24 h |
| Nachkontrolle nur per RPC (`outcome`, Halterzahl nach 15 min) | kostet Budget, misst nur Halter | Nachlauf von DexScreener ohne RPC, Graduation ohne RPC |
| Keine Zweitmeinung zum Risiko | ob ein externer Score über das Fair-Gate hinaus trennt, ist ungemessen | Rugcheck je GO/GESPERRT, record-only, Trennung im Report |

## 2. Angebundene Quellen

| Quelle | Zugang | Liefert | Kosten, Limits | Beleg (abgerufen 2026-10-04) | Im Sniper |
|---|---|---|---|---|---|
| **PumpPortal Migrationsfeed** `subscribeMigration` auf `wss://pumpportal.fun/api/data` | WebSocket, dieselbe Verbindung wie `subscribeNewToken`, kein Schlüssel | jede Migration von der Bonding Curve zu einem AMM-Pool (= Graduation), plattformweit | kostenlos [Snippet]; Nachrichtenzahl ≈ Graduierungen je Tag (Grundrate × Launches, grob 100–300) | [Snippet] pumpportal.fun/data-api/real-time („fires when a token migrates from the bonding curve to an AMM pool"); Feldnamen des Ereignisses **NICHT VERIFIZIERT** → Zeile trägt `roh` | `live --extern DATEI`: Zeile `graduierung` mit `alarm` (höchster eigener Tier aus dem Alarm-Gedächtnis, 5 000 Einträge) ; Statuszeile „Graduierungen (PumpPortal)" |
| **DexScreener** `GET /latest/dex/tokens/{bis 30 Mints}` | REST, kein Schlüssel | Paare je Token: DEX (`pumpfun` = noch auf der Kurve, `pumpswap`/`raydium` = graduiert), Preis, Liquidität, MC, Volumen | 300 Anfragen je Minute [Snippet, docs/dexscreener_paid.md] | Referenz-Spiegel, siehe `docs/dexscreener_paid.md`; Parser `dexpaid.best_pair`/`snapshot_row` seit 0.3.3 | `quellen nachlauf RECORDS --extern DATEI [--tape TAPE]`: eine Zeile `nachlauf` je Coin und Horizont (+1 h, +24 h), Alarme vor Kontrollen, idempotent, `--max 3000`, `--je-minute 250` |
| **Rugcheck** `GET https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary` | REST, lesen laut Drittanleitungen ohne Schlüssel | `score`, `score_normalised` (0–100, höher = riskanter), `risks[]` (Name, Stufe, Punkte), `rugged` | kostenlos für Lese-Endpunkte [Snippet]; Rate-Limit **NICHT VERIFIZIERT** | [Snippet] Drittanleitungen (qodex.ai, cryptouniversity.network, solanatracker.io), kein Zugriff auf api.rugcheck.xyz/swagger | `live --extern DATEI --rugcheck`: je GO/GESPERRT eine Zeile `risiko` (einmal je Token, HTTP-Gruppe außerhalb des RPC-Budgets); bei unerwarteter Antwortform `roh` |

Zeilentypen der Außenquellen-Datei (JSONL, append-only, getrennt von Records und Tape): `feed` (verbunden/getrennt),
`graduierung`, `nachlauf`, `risiko`. `quellen zeigen DATEI` fasst sie zusammen.

## 3. Grundraten (zur Einordnung der Kontroll-Stichprobe)

| Kennzahl | Wert | Quelle | Kennzeichnung |
|---|---|---|---|
| Graduation-Rate aller pump.fun-Launches, Mitte Juni 2026 | ≈ 0,26 % | dextools.io/news („Pump.fun in 2026: Graduation Rate Collapses to 0.26%", Dune-Daten) | [Snippet] |
| Wochenhoch 2026 | ≈ 1,15 % | bitget.com/news („graduating tokens break to 1.15% of new launches") | [Snippet] |
| historisch | ≈ 1,4 %; „unter 2 %" | bitget.com/news (Dune), solanacompass.com | [Snippet] |

`tape report --extern` vergleicht den Graduation-Anteil der Kontroll-Stichprobe mit dem Band 0,26–1,4 %; liegt er weit
außerhalb, stimmt etwas mit der Stichprobe (`--tape-sample`) oder dem Feed nicht.

## 4. Nicht gebaut (mit Grund)

| Quelle | Grund | Stand |
|---|---|---|
| Telegram-Call-Kanäle (Mitlesen) | braucht den Account des Nutzers (Eskalationspunkt 2) und trägt ToS-Risiko (7); Hypothese von EXP001 – vorab im Sniper genutzt würde der Test sich selbst prüfen | E-005: erst nach EXP001-Freeze, record-only |
| X-API | Geld (Eskalationspunkt 1) | E-005: nein |
| Birdeye OHLCV | Abdeckung der Kurve NICHT VERIFIZIERT, Kauf ist Eskalation | E-006: Free-Tier-Pilot zuerst |
| pump.fun Frontend-API | inoffiziell, JWT nötig, Rate-Limit-Header (docs/exp002_data_sources.md) | nicht |
| Bitquery, Dune (API) | Geld | nicht |
| GeckoTerminal `https://api.geckoterminal.com/api/v2/networks/{n}/tokens/{a}/pools`, `/pools/{p}/ohlcv/{tf}` | Pfade [direkt geprüft im Client-Code raw.githubusercontent.com/dineshpinto/geckoterminal-api/main/geckoterminal_api/api.py, 2026-10-04]; 30 Aufrufe je Minute [Snippet apiguide.geckoterminal.com/faq, pkg.go.dev kkyr/coingecko-api]; OHLCV rückwirkend abrufbar | Kandidat für einen OHLCV-Nachlauf, falls DexScreener Kurven-Coins nicht abdeckt (Prüfpunkt e in OQ-033) |

## 5. Verifikation in der ersten Live-Minute (Rechner des Nutzers)

1. Start mit `--extern aussen.jsonl`. Die Startzeile nennt „Außenquellen aussen.jsonl". Innerhalb von etwa 30 Minuten
   muss die Statuszeile `Graduierungen (PumpPortal) > 0` zeigen (Grundrate × Launches je Stunde). Bleibt sie bei 0, lehnt
   PumpPortal `subscribeMigration` ab oder sendet ohne `mint`/`txType`: `quellen zeigen aussen.jsonl` und die `roh`-Felder
   der ersten Zeilen prüfen, Feldnamen in OQ-033 nachtragen.
2. `quellen nachlauf live.jsonl --extern aussen.jsonl --tape live_tape.jsonl --dry-run` zeigt fällige Schnappschüsse und die
   Zahl der Anfragen; ohne `--dry-run` laufen sie. Zeilen mit `fehlt` bei Coins, die noch auf der Kurve sind, zeigen, ob
   DexScreener Kurven-Coins abdeckt (Prüfpunkt e).
3. Mit `--rugcheck`: die erste `risiko`-Zeile hat `status 200` und `score_norm`; sonst steht die Antwort in `roh`.

## 6. Lesarten im `tape report --extern`

- **Beurteilbar / offen:** Der Feed sieht nur, solange der Sniper läuft. Ein Alarm zählt erst, wenn der Feed davor lief
  und danach noch 24 h (`FEED_REIFE_S`); jüngere Alarme stehen als „offen". Trennungen (`feed getrennt/verbunden`)
  werden summiert. Zweiter Marker ohne Laufzeitbezug: ein Nachlauf-Paar auf einer anderen DEX als `pumpfun`.
- **Graduation extern vs. im Tape-Fenster:** Das Tape endet nach 240 s; die Außenquelle zählt auch spätere Graduierungen.
- **Nachlauf:** „lebt" = Paar vorhanden und Liquidität ≥ 1 000 USD (Annahme, OQ-033). Verspätete Zeilen (Alter über dem
  doppelten Horizont) werden gezählt, nicht still verworfen.
- **Kurvenadresse statt Mint:** `profil bauen` lädt die Historie über `getSignaturesForAddress(bonding_curve)`. In der
  IDL `pump.json` steht `bonding_curve` in den Konten von `create`, `create_v2`, `buy`, `sell` und `migrate`
  [direkt geprüft über raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump.json, 2026-10-04]; die Historie der
  Kurve ist also vollständig und endet mit der Migration, während der Mint danach alle PumpSwap-Trades sammelt.
- **Rugcheck:** GO-Coins am Median des Scores geteilt, Trefferquote (Primärzeile +30 s/+300 s) je Hälfte mit Wilson. Eine
  Lesart gibt es erst ab 20 GO je Hälfte. Trennt der Score nicht, bleibt er informativ; trennt er, folgt eine Zeitsplit-Prüfung
  wie beim Profil, bevor er ein Gate wird (R2, R4).

## 7. Abgrenzung zu `outcome`

`outcome --file live.jsonl` (seit 0.1) prüft per RPC nach 15 Minuten die Halterzahl und den Kurvenstand und hängt
`outcome_for`-Zeilen an die Records. Es bleibt bestehen (Halterwachstum ist ein eigenes Maß), kostet aber Budget. Die
Außenquellen messen ohne RPC und über längere Horizonte; sie ersetzen `outcome` nicht, sie ergänzen es.

## 8. Befehle

```bash
python -m holder_scorer live --stufe 1 --tiers go,widerruf,rug,gesperrt --notify go,widerruf,rug --telegram --extern aussen.jsonl \
  --record live.jsonl --tape live_tape.jsonl --tape-sample 0.1 --budget 1000 --paper papier.jsonl --paper-latency 30
python -m holder_scorer quellen zeigen aussen.jsonl
python -m holder_scorer quellen nachlauf live.jsonl --extern aussen.jsonl --tape live_tape.jsonl --dry-run
python -m holder_scorer quellen nachlauf live.jsonl --extern aussen.jsonl --tape live_tape.jsonl
python -m holder_scorer tape report live.jsonl live_tape.jsonl --extern aussen.jsonl
python -m holder_scorer profil bauen --tape live_tape.jsonl --extern aussen.jsonl --rpc URL --max-mints 20 --out profil.json
```

`--rugcheck` ist opt-in und braucht `--extern`. Nichts davon kauft, bezahlt oder sendet Schlüssel.
