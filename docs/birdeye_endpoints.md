# Birdeye Data Services – OHLCV-Endpoints (Solana), CU-Kosten, Limits, Pläne

Stand der Recherche: **2026-09-29**. Zweck: Datenquelle für EXP001 (Kursreaktion nach Telegram-Calls,
Primärhorizont 1 h, mindestens 200 Events inkl. Baselines) dimensionieren. **Nur Empfehlung, kein Kauf.**

## 0. Quellenlage (bitte zuerst lesen)

Die Netzwerk-Policy der Arbeitsumgebung hat am 2026-09-29 alle Birdeye-Hosts (`docs.birdeye.so`,
`bds.birdeye.so`, `public-api.birdeye.so`, `birdeye.so`, `data.birdeye.so`) für den Direktabruf
gesperrt (siehe OPEN_QUESTIONS.md, OQ-007). Alle Angaben in diesem Dokument stammen daher aus
**WebSearch-Snippets der genannten offiziellen Seiten** und sind mit **[Snippet]** gekennzeichnet; sie
gelten formal als nicht direkt verifiziert. Angaben, die nur bei Drittanbietern zu finden waren, tragen
**[Drittquelle]**. Was in keiner Quelle belegbar war, steht als **NICHT VERIFIZIERT**. Nichts in diesem
Dokument stammt aus dem Gedächtnis.

Vor einer Kaufentscheidung oder einem Freeze, der auf einer dieser Zahlen aufbaut, sind die Seiten
direkt zu prüfen (Host-Freigabe in den Environment-Einstellungen, dann `docs.birdeye.so/llms.txt`
bzw. die Seiten mit angehängtem `.md`; dieser Hinweis selbst ist [Snippet], Quelle: https://docs.birdeye.so/,
abgerufen 2026-09-29).

## 1. Endpoints

Basis-URL: `https://public-api.birdeye.so` [Snippet] (Quelle: https://docs.birdeye.so/reference/get-defi-ohlcv,
abgerufen 2026-09-29). Header: `X-API-KEY: <key>` und `x-chain: solana` [Snippet] (Quelle:
https://docs.birdeye.so/docs/trending-tokens, abgerufen 2026-09-29). Default-Chain ohne `x-chain`:
NICHT VERIFIZIERT. Zeitparameter `time_from`/`time_to` als Unix-Sekunden: nur [Drittquelle]
(Quelle: https://pkg.go.dev/github.com/tigusigalpa/birdeye-go/price, abgerufen 2026-09-29), offiziell
NICHT VERIFIZIERT.

| Endpoint | Methode | Zweck | Max. Datensätze pro Call | Beleg |
|---|---|---|---|---|
| `/defi/v3/ohlcv` | GET | OHLCV V3 je Token | **5 000 Kerzen** | Limit [Snippet] (Quelle: https://docs.birdeye.so/changelog/20250717-enhanced-free-access-performance-improvements-and-evm-data-accuracy, abgerufen 2026-09-29); exakter Pfad nur [Drittquelle] (pkg.go.dev, s. o.), Referenzseite https://docs.birdeye.so/reference/get-defi-v3-ohlcv nicht im Suchindex |
| `/defi/v3/ohlcv/pair` | GET | OHLCV V3 je Pool/Pair | 5 000 Kerzen [Snippet] | Pfad [Snippet] (Quelle: Changelog 2025-07-17, s. o.); für Standard-Nutzer freigeschaltet [Snippet] (gleiche Quelle) |
| `/defi/v3/ohlcv/base-quote` | – | – | – | **NICHT VERIFIZIERT**; existiert offenbar nicht. Base/Quote nur als Legacy `/defi/ohlcv/base_quote` |
| `/defi/ohlcv` (Legacy) | GET | OHLCV je Token | **1 000 Records** [Snippet] | Quelle: https://docs.birdeye.so/reference/get-defi-ohlcv, abgerufen 2026-09-29 |
| `/defi/ohlcv/pair` (Legacy) | GET | OHLCV je Pair | NICHT VERIFIZIERT | Erwähnung [Snippet] (Changelog 2025-07-17, s. o.) |
| `/defi/ohlcv/base_quote` (Legacy) | GET | OHLCV Base/Quote | 1 000 Records [Snippet] | Quelle: https://docs.birdeye.so/reference/get-defi-ohlcv-base_quote, abgerufen 2026-09-29 |

Deprecation der Legacy-Endpoints zugunsten V3: offiziell **NICHT VERIFIZIERT**; ein Community-SDK
bezeichnet `/defi/ohlcv` und `/defi/ohlcv/pair` als "upstream-deprecated" [Drittquelle] (Quelle:
https://github.com/tigusigalpa/birdeye-go, abgerufen 2026-09-29). Für EXP001 wird **V3** verwendet.

### 1.1 Parameter OHLCV V3 (Token)

| Parameter | Werte / Bedeutung | Beleg |
|---|---|---|
| `address` | Token-Mint | [Drittquelle] pkg.go.dev, s. o. |
| `type` | Intervall: `1s, 15s, 30s, 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 8H, 12H, 1D, 3D, 1W, 1M` | 1m…1M [Snippet] (Quelle: https://docs.birdeye.so/docs/websocket, abgerufen 2026-09-29); 1s/15s/30s zusätzlich für V3 auf Solana [Snippet] (Quelle: https://docs.birdeye.so/changelog/new-ohlcv-endpoints-on-solana, abgerufen 2026-09-29) |
| `time_from`, `time_to` | Unix-Zeitstempel (Sekunden: [Drittquelle]) | s. o. |
| `mode` | `range` (Default) oder `count` | Parameter existiert [Snippet] (Quelle: https://docs.birdeye.so/changelog/20250723-meme-token-apis-ohlcv-enhancements-cjk-search-fix, abgerufen 2026-09-29); Werte [Drittquelle] |
| `count_limit` | 0–5 000, Default 5 000 | Parameter [Snippet] (gleiche Quelle); Wertebereich [Drittquelle] |
| `padding` | Default `false` – leere Kerzen werden ohne Padding **nicht** geliefert | Parameter [Snippet]; "empty candles are not displayed" [Snippet] (Quelle: Changelog new-ohlcv-endpoints-on-solana, s. o.) |
| `outlier` | Default `true` | Parameter [Snippet]; Default [Drittquelle] |
| `currency` | `usd` (Default) oder `native` | [Drittquelle] |
| `ui_amount_mode` | `raw` / `scaled` / `both` (Solana, Token-2022 Scaled-UI) | Einführung 2025-07-02 "to select endpoints" [Snippet] (Quelle: https://docs.birdeye.so/changelog/20250702-support-for-scaled-ui-amounts-in-solana-token-2022, abgerufen 2026-09-29); Geltung für OHLCV V3 NICHT VERIFIZIERT |

Response-Felder V3: `o, h, l, c, v, v_usd, unix_time, address, type, currency` (Token zusätzlich
`scaled_*`), Envelope `items[]` – [Drittquelle] (pkg.go.dev, s. o.). Offiziell belegt: neues Feld `v_usd`
in V3-Responses [Snippet] (Quelle: https://docs.birdeye.so/changelog/expanded-ohlcv-v3-coverage-and-usd-volume-metrics,
abgerufen 2026-09-29).

**Wichtig für EXP001:** Ohne `padding` fehlen Minuten ohne Trades. Für Reaktionsfenster auf illiquiden
Token muss das Auswerteskript fehlende Kerzen explizit behandeln (Forward-Fill oder "kein Trade").

### 1.2 Maximaler Zeitraum pro Call

Offiziell gibt es nur Mengenlimits (1 000 Records Legacy, 5 000 Kerzen V3) [Snippet]; eine Zeitraum-Regel
ist NICHT VERIFIZIERT. Abgeleitet: 5 000 × 1m = 3,47 Tage pro Call; 5 000 × 1s = 83 Minuten;
1 000 × 1m = 16,7 Stunden.

### 1.3 Datenhistorie / Retention

- Sub-Minute-Intervalle: 1s bis zu 2 Wochen, 15s/30s bis zu 3 Monate [Snippet] (Quelle:
  https://docs.birdeye.so/changelog/new-ohlcv-endpoints-on-solana, abgerufen 2026-09-29; identisch im
  Blogpost https://bds.birdeye.so/blog/detail/introducing-sub-minute-intervals-in-birdeye-data-services-ohlcv-v3-apis).
- Solana-Sub-Minute-Daten ab 2025-05-02 16:30 UTC; V3 auf ETH/BSC/Base ab 2025-05-09 [Snippet] (Quelle:
  https://docs.birdeye.so/changelog/expanded-ohlcv-v3-coverage-and-usd-volume-metrics, abgerufen 2026-09-29).
- **Historientiefe für 1m-Kerzen und Historientiefe je Plan: NICHT VERIFIZIERT** → OQ-005. Für
  vergangene EXP001-Events ist das der kritische Punkt; vor dem Freeze mit dem Free-Tier prüfen.
- **Abdeckung der Pump.fun-Bonding-Curve (Trades vor Graduation) durch Birdeye-OHLCV: MUSS VERIFIZIERT
  WERDEN** (OQ-005). Falls Calls auf frische Pump.fun-Token zielen, entscheidet das über die Eignung.

## 2. Compute-Unit-Kosten (CU)

Definition: "Compute units are a measure of the computational resources consumed by each API call…"
[Snippet] (Quelle: https://docs.birdeye.so/docs/compute-unit-cost, abgerufen 2026-09-29).

| Endpoint | CU pro Call | Beleg |
|---|---|---|
| `/defi/v3/ohlcv` | **NICHT VERIFIZIERT** | CU-Tabelle war nicht im Snippet enthalten |
| `/defi/v3/ohlcv/pair` | **NICHT VERIFIZIERT** | – |
| `/defi/ohlcv` (Legacy) | 40 CU [Drittquelle; Host bei erneuter Prüfung am 2026-09-29 nicht erreichbar] | Quelle: https://skills.lc/agiprolabs/claude-trading-skills/agiprolabs-claude-trading-skills-skills-birdeye-api-skill-md, abgerufen 2026-09-29 |
| `/defi/price` (Anker) | 3 CU [Snippet] | Quelle: https://docs.birdeye.so/reference/get-defi-price, abgerufen 2026-09-29 |
| `/defi/v3/token/txs` (Anker) | 12 CU [Snippet] | Quelle: https://data.birdeye.so/docs/data-api/transactions/get-defi-v3-token-txs, abgerufen 2026-09-29 |
| Batch-/Multi-APIs | `ceil(N^0.8 × Basis-CU)` [Snippet] | Quelle: https://docs.birdeye.so/docs/batch-token-cu-cost, abgerufen 2026-09-29 |

Skalierung der V3-OHLCV-Kosten mit der Anzahl gelieferter Kerzen: NICHT VERIFIZIERT (kein Beleg
gefunden). Seit 2025-10-13 gibt es einen Utility-Endpoint für den eigenen CU-Verbrauch (aktueller Zyklus,
Rest, Overage, Verlauf 1 Jahr) [Snippet] (Quelle: https://docs.birdeye.so/changelog/20251013-release-credits-usage,
abgerufen 2026-09-29) → der reale OHLCV-CU-Preis lässt sich im Free-Tier-Pilot **messen**.

## 3. Rate-Limits

- Limit gilt auf Account-Ebene über alle APIs [Snippet] (Quelle: https://docs.birdeye.so/docs/rate-limiting,
  abgerufen 2026-09-29).
- Je Plan (Pricing-Seite) [Snippet]: Lite 15 rps, Starter 15 rps, Premium 50 rps, Business 100 rps,
  Enterprise 1 000+ rps (Quellen: https://bds.birdeye.so/pricing und https://birdeye.so/data-api/pricing,
  abgerufen 2026-09-29). Free/Standard: 1 rps [Snippet] (Quelle:
  https://bds-support.birdeye.so/hc/en-us/articles/46936561906073-Your-Complete-Guide-to-Account-Creation,
  abgerufen 2026-09-29).
- Per-Endpoint-Limits existieren (z. B. `/defi/price` 300 rps, `/defi/history_price` 100 rps) [Snippet]
  (Quelle: https://docs.birdeye.so/docs/per-api-rate-limit, abgerufen 2026-09-29); OHLCV-Zeilen:
  NICHT VERIFIZIERT.

## 4. Pläne und Preise

Alle Werte [Snippet] von https://bds.birdeye.so/pricing (identisch auf https://birdeye.so/data-api/pricing),
abgerufen 2026-09-29, sofern nicht anders markiert.

| Plan | Preis/Monat | Inkl. CU/Monat | Rate-Limit | Overage | Max. Nutzung/Monat | Bemerkung |
|---|---|---|---|---|---|---|
| Standard (Free) | 0 USD | 30 000 ¹ | 1 rps ¹ | – | – | Zugriff auf 20+ Endpoints inkl. OHLCV V3 Pair [Snippet, Changelog 2025-07-17]; OHLCV V3 Token für Free: NICHT VERIFIZIERT |
| Lite | 39 USD | 2 500 000 | 15 rps | 15 USD / 1 Mio. CU | 7,5 Mio. | kein WebSocket |
| Starter | 99 USD | 8 000 000 | 15 rps | 12 USD / 1 Mio. CU | 24 Mio. | – |
| Premium | 199 USD | 20 000 000 | 50 rps | 9,90 USD / 1 Mio. CU | 100 Mio. | 500 WS-Verbindungen |
| Business | 499 USD | 60 000 000 | 100 rps | 6,90 USD / 1 Mio. CU | "40B" ² | Batch-APIs, Autoscale |
| Enterprise | auf Anfrage | individuell | 1 000+ rps | gestaffelt | – | CSV-Export, 24/7 Support |

¹ Quelle: Support-Artikel "Your Complete Guide to Account Creation" (s. Abschnitt 3), [Snippet].
² So im Snippet; unplausibel, vor Verwendung prüfen.

Weitere Konditionen [Snippet]: Rabatte 10 % (3 Monate), 20 % (6 Monate), 30 % (12 Monate) (Quelle:
bds.birdeye.so/pricing); nicht genutzte CU werden bei Upgrade/Downgrade/Kündigung nicht übertragen
(Quelle: https://docs.birdeye.so/docs/subscription-changes, abgerufen 2026-09-29); Overage ist
Post-paid mit automatischer Abbuchung ab Schwelle (Quelle: https://docs.birdeye.so/docs/overage-charge-rule,
abgerufen 2026-09-29); Datenzugang nach Paket: Lite/Starter nur "multiple price" unter den
Batch-APIs, übrige Batch-/Multi-APIs ab Business (Quelle: https://docs.birdeye.so/docs/data-accessibility-by-packages,
abgerufen 2026-09-29). **x402 Pay-per-Request: 0,003 USD pro Request** für die gesamte REST-API ohne
Abo, kein WebSocket [Snippet] (Quelle: https://birdeye.so/data-api/blog/detail/introducing-x402-on-birdeye-data-pay-per-request-api-access,
abgerufen 2026-09-29); Historientiefe unter x402: NICHT VERIFIZIERT.

## 5. CU-Bedarf für EXP001 (parametrisch)

Die Baseline-Definition der Prereg v0.3 liegt nicht vor (OQ-001, OQ-004). Die Rechnung ist deshalb als
Sensitivitätstabelle aufgebaut; Annahmen sind markiert.

**Annahmen**

- E = Anzahl Events (Minimum laut Auftrag 200; Vergleich 1 000).
- Kerzenintervall 1m; Pre-Window P = 60 min (Pre-Trend/Normalisierung); Horizont H ∈ (1 h, 4 h, 24 h);
  Kerzen pro Event = P + H = 120 / 300 / 1 500.
- Calls pro Event-Serie: `calls = ceil((P + H) / R_max)` mit R_max = 5 000 (V3) bzw. 1 000 (Legacy)
  → V3: 1 Call für alle drei Horizonte; Legacy: 1 / 1 / 2 Calls.
- Baseline-Variante (i): zeitversetzte Fenster desselben Tokens (z. B. 3 Fenster gleicher Länge vor dem
  Event) → dieselbe Serie, Fenster breiter: 4 × (P + H) ≤ 6 000 Kerzen → V3: 1 Call (H ≤ 4 h) bzw.
  2 Calls (H = 24 h). Warnung: solche Baselines sind mit dem Event-Fenster autokorreliert; nur mit
  klarer Trennung im Design verwenden.
- Baseline-Variante (ii): k gematchte Zufalls-Token je Event, k ∈ (1, 3, 5) → k zusätzliche Serien à
  1 Call (V3).
- Overhead: 5 % Retries; optional 1 Metadaten-/Overview-Call je Serie (CU dafür NICHT VERIFIZIERT,
  separat ausgewiesen).
- CU pro OHLCV-Call: **NICHT VERIFIZIERT** → Szenarien 40 (Drittquelle), 100, 200.

**Calls (V3, H = 1 h, 5 % Retries, ohne Metadaten-Calls)**

| E | k = 0 | k = 1 | k = 3 | k = 5 |
|---|---|---|---|---|
| 200 | 210 | 420 | 840 | 1 260 |
| 1 000 | 1 050 | 2 100 | 4 200 | 6 300 |

Metadaten-Calls kämen mit E·(1+k)·1,05 hinzu (E = 200, k = 5: +1 260 Calls inkl. Retries). Für H = 4 h ändert sich bei V3
nichts; für H = 24 h nur bei Legacy (×2) bzw. Variante (i) (×2).

**CU-Bedarf für OHLCV-Calls (V3, H = 1 h)**

| Szenario | 40 CU/Call | 100 CU/Call | 200 CU/Call |
|---|---|---|---|
| E = 200, k = 0 (210 Calls) | 8 400 | 21 000 | 42 000 |
| E = 200, k = 1 (420) | 16 800 | 42 000 | 84 000 |
| E = 200, k = 3 (840) | 33 600 | 84 000 | 168 000 |
| **E = 200, k = 5 (1 260)** | **50 400** | **126 000** | **252 000** |
| E = 1 000, k = 5 (6 300) | 252 000 | 630 000 | 1 260 000 |

**Abgleich mit den Plänen**

| Plan | CU/Monat | Reicht für E = 200, k = 5? | Monate nötig (Worst Case 252 000 CU) | Sammeldauer 1 260 Calls |
|---|---|---|---|---|
| Standard (Free), 30 000 CU, 1 rps | 30 000 | nein (nur k = 0 bei ≤ 100 CU/Call oder k = 1 bei 40 CU/Call) | 9 | ca. 21 min |
| **Lite, 2,5 Mio. CU, 15 rps, 39 USD** | 2 500 000 | **ja, > 9× Puffer**; auch E = 1 000, k = 5 bei 200 CU/Call | 1 | < 2 min (Per-Endpoint-Limit NICHT VERIFIZIERT) |
| Starter, 8 Mio. CU, 99 USD | 8 000 000 | ja | 1 | – |
| x402, 0,003 USD/Request | – | 1 260 × 0,003 = 3,78 USD (mit Metadaten-Calls 2 520 × 0,003 = 7,56 USD) | – | Zahlungsabwicklung on-chain nötig; Historientiefe NICHT VERIFIZIERT |

**Empfehlung (kein Kauf):** Für EXP001 mit ≥ 200 Events und Baselines reicht **Lite (39 USD/Monat)**
unter allen betrachteten CU-Szenarien mit großem Puffer; das Experiment ist einmalig, ein Monat genügt
(keine Übertragung ungenutzter CU). **Vorher** im Free-Tier einen Pilot mit ca. 20 Events fahren und
dabei (a) den tatsächlichen CU-Preis pro OHLCV-Call über den Credits-Usage-Endpoint messen, (b) die
Verfügbarkeit von 1m-Kerzen für die Event-Zeitpunkte prüfen (Retention, OQ-005) und (c) prüfen, ob
Pump.fun-Kurventrades in den Kerzen enthalten sind. Erst danach Plan wählen. x402 ist die günstigste
Alternative, hängt aber an ungeprüfter Historientiefe und zusätzlicher Zahlungsinfrastruktur.

## 6. Offene Punkte

Siehe OPEN_QUESTIONS.md: OQ-004 (Baseline/Horizonte), OQ-005 (CU/Call, Retention, Pump.fun-Abdeckung),
OQ-006 (Plan-Entscheidung), OQ-007 (Direktverifikation nach Host-Freigabe).

## 7. Quellenverzeichnis (alle abgerufen 2026-09-29; Status: Snippet = Seite nicht direkt abrufbar)

Offiziell (nur Snippet):
- https://docs.birdeye.so/ · https://docs.birdeye.so/reference/get-defi-ohlcv ·
  https://docs.birdeye.so/reference/get-defi-ohlcv-base_quote · https://docs.birdeye.so/reference/get-defi-price
- https://docs.birdeye.so/docs/trending-tokens · https://docs.birdeye.so/docs/websocket ·
  https://docs.birdeye.so/docs/compute-unit-cost · https://docs.birdeye.so/docs/batch-token-cu-cost
- https://docs.birdeye.so/docs/rate-limiting · https://docs.birdeye.so/docs/per-api-rate-limit ·
  https://docs.birdeye.so/docs/data-accessibility-by-packages · https://docs.birdeye.so/docs/subscription-changes ·
  https://docs.birdeye.so/docs/overage-charge-rule
- https://docs.birdeye.so/changelog/new-ohlcv-endpoints-on-solana ·
  https://docs.birdeye.so/changelog/expanded-ohlcv-v3-coverage-and-usd-volume-metrics ·
  https://docs.birdeye.so/changelog/20250717-enhanced-free-access-performance-improvements-and-evm-data-accuracy ·
  https://docs.birdeye.so/changelog/20250723-meme-token-apis-ohlcv-enhancements-cjk-search-fix ·
  https://docs.birdeye.so/changelog/20250702-support-for-scaled-ui-amounts-in-solana-token-2022 ·
  https://docs.birdeye.so/changelog/20251013-release-credits-usage
- https://bds.birdeye.so/pricing · https://birdeye.so/data-api/pricing ·
  https://bds.birdeye.so/blog/detail/introducing-sub-minute-intervals-in-birdeye-data-services-ohlcv-v3-apis ·
  https://birdeye.so/data-api/blog/detail/introducing-x402-on-birdeye-data-pay-per-request-api-access ·
  https://bds-support.birdeye.so/hc/en-us/articles/46936561906073-Your-Complete-Guide-to-Account-Creation ·
  https://data.birdeye.so/docs/data-api/transactions/get-defi-v3-token-txs ·
  https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-multi-price

Drittquellen (vom Recherche-Agenten am 2026-09-29 abgerufen; skills.lc war bei erneuter Prüfung nicht erreichbar):
- https://pkg.go.dev/github.com/tigusigalpa/birdeye-go/price · https://github.com/tigusigalpa/birdeye-go
- https://skills.lc/agiprolabs/claude-trading-skills/agiprolabs-claude-trading-skills-skills-birdeye-api-skill-md
