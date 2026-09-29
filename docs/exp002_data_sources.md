# EXP002 – Datenquellen für einen historischen Pump.fun-Backtest (Vergleich und Empfehlung)

Stand der Recherche: **2026-09-29**. Zweck: Datenquelle für `PREREGISTRATION_EXP002.md` (Dev-Follow,
Paper-only) auswählen. **Nur Empfehlung, kein Kauf.**

## 0. Quellenlage

Die Netzwerk-Policy der Arbeitsumgebung sperrte am 2026-09-29 die Websites aller Anbieter
(helius.dev, bitquery.io, dune.com, flipsidecrypto.xyz, quicknode.com, triton.one, shyft.to,
chainstack.com, allium.so, goldsky.com, moralis.com, pumpportal.fun, solana.com, docs.jito.wtf) sowie
News-/Paper-Seiten (OPEN_QUESTIONS.md OQ-007). Erreichbar waren `github.com`, `raw.githubusercontent.com`,
`registry.npmjs.org`, `pypi.org` (kanonische Host-Liste: OPEN_QUESTIONS.md OQ-007). Deshalb gilt:

- **[direkt geprüft]** = aus dem offiziellen GitHub-Repository des Anbieters (z. B. Helius-Doku-Quellen in
  `helius-labs/core-ai`, Dune-Spellbook-SQL, Bitquery-Beispiel-Repo, Pump.fun-`pump-public-docs`).
- **[Snippet]** = nur WebSearch-Snippet der genannten URL, Seite nicht abrufbar.
- **[Drittquelle]** = z. B. api-evangelist-Profile (dort teils als "unreconciled" markiert).
- **NICHT VERIFIZIERT** (NV) = nicht belegbar. **Preise sind fast durchgehend NV oder Drittquelle**
  und vor jeder Entscheidung direkt zu prüfen.

## 1. Datenbedarf aus EXP002

Pflichtfelder je Launch (Definitionen in `PREREGISTRATION_EXP002.md`):

| Bedarf | Feld/Ereignis | Warum |
|---|---|---|
| Create-Event (Instruktionen `create` **und** `create_v2`) | mint, bonding_curve, **creator**, user (Signer), **is_holder_reward**, slot, block_time, tx_index, virtuelle/reale Startreserven, quote_mint | Population, Dev-Identität (bei Holder-Rewards-Coins ist `creator` eine PDA → Dev = user, OQ-023), Initialzustand, SOL-Quote-Filter |
| Trades (erste 60 min + Exit-Horizont) | is_buy, sol_amount, token_amount, user, slot, block_time, tx_index, virtuelle/reale Reserven **nach** dem Trade, Fee-Felder | Kurvenzustand bei Entry/Exit, Replay, Self-Buy, Simulator-Validierung |
| Complete-Event / Migration | mint, slot, block_time | Graduation (7-Tage-Regel), Exit-Sonderfall |
| Dev-Historie | alle Creates + Completes im rollierenden 90-Tage-Lookback vor jedem Event | point-in-time Graduation-Quote je Dev |
| Basisrate | alle Creates + Completes im Vorzeitraum | Graduation-Basisrate aus eigenen Daten (OQ-019) |

Die Events sind im Programm `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` als Anchor-Events kodiert:
CreateEvent (u. a. `creator`, `timestamp`, Startreserven, `quote_mint`), TradeEvent (u. a. `sol_amount`,
`token_amount`, `is_buy`, `user`, `timestamp`, `virtual_sol_reserves`, `virtual_token_reserves`,
`real_sol_reserves`, `real_token_reserves`, `fee_basis_points`, `fee`, `creator_fee_basis_points`,
`creator_fee`), CompleteEvent, CompletePumpAmmMigrationEvent [direkt geprüft über die aus der offiziellen
IDL generierten Codama-Decoder, Quelle: https://raw.githubusercontent.com/sevenlabs-hq/carbon/main/decoders/pumpfun-decoder/src/types/trade_event.rs
und .../create_event.rs, abgerufen 2026-09-29; IDL selbst: https://github.com/pump-fun/pump-public-docs/tree/main/idl].
Die offizielle IDL (Refresh 2026-09-12) enthält zusätzlich `holder_rewards_bps`/`holder_rewards` (TradeEvent) und
`creator_fee_bps`/`is_holder_reward` (CreateEvent) [direkt geprüft: https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump.json];
die Carbon-Feldlisten sind insoweit veraltet. Ältere Event-Layouts (ohne `creator`/`timestamp`) existieren [direkt geprüft:
https://raw.githubusercontent.com/rckprtr/pumpdotfun-sdk/main/src/IDL/pump-fun.json] – Decoder müssen
versionsfest sein. Die Blockzeit ist auf Solana sekundengenau und geschätzt ("stake-weighted mean of the
Vote timestamps") [direkt geprüft: https://raw.githubusercontent.com/solana-foundation/solana-com/main/apps/docs/content/docs/en/rpc/http/getblocktime.mdx,
abgerufen 2026-09-29]; die Reihenfolge innerhalb einer Sekunde ergibt sich aus (slot, tx_index).

**Volumen (Größenordnung, NV):** Snippet-Zahlen nennen 655 770 Creates im September 2025 und 832 941
"terminale" Launches zwischen 2026-05-08 und 2026-06-10 (Quellen: https://arxiv.org/html/2602.14860v1 und
https://zenodo.org/records/21383616, nur Snippet) → ca. 20 000–25 000 Creates pro Tag. Ein 30-Tage-Fenster
plus 97 Tage Lookback/Reifung sind damit ca. 2,5–3,2 Mio. Creates (nur Create-/Complete-Felder), aber
Trade-Details werden nur für Treatment-Events (≥ 200) und ihre Kontrollen (k = 5) benötigt: ca. 1 200
Launches × erste Stunde.

## 2. Vergleichstabelle

Legende: ✓ belegt, ~ abgeleitet/Drittquelle, NV nicht verifiziert, ✗ nicht vorhanden.

| Quelle | Create + Creator | Trades sekundengenau (slot, block_time) | Complete/Migration | Historie | Preis/Monat, Free-Tier | Limits/Credits | Format |
|---|---|---|---|---|---|---|---|
| **Dune** (Spellbook `pumpdotfun_solana` + eigene SQL auf `solana.instruction_calls`) | ~ Spellbook erkennt nur `create`, nicht `create_v2`; Population + Creator per eigener SQL über den CreateEvent-Diskriminator | ✓ `block_time`, `block_slot`, `tx_index`; Spellbook nur virtuelle Reserven, reale Reserven/Fees per eigener Dekodierung | ~ (CompleteEvent decodierbar; dekodierte Tabellen NV) | ✓ ab 2024-01-14 | Free evtl. nur Lesezugriff seit 2026-09-10 (NV); Analyst 75 USD, Plus 399 USD (NV/Drittquelle) | Credits pro Query/Export (Drittquelle) | SQL, API, CSV |
| **Helius** (RPC + Enhanced/`getTransactionsForAddress`) | ✓ per eigenem Decoding der Roh-Tx | ✓ slot + blockTime | ✓ per Decoding | Archiv-RPC (Tiefe NV); LaserStream nur 24 h Replay | Developer 49 USD (10 Mio. Credits) ✓; Business 499 USD; Free ~ | Enhanced-API 100 Credits/Call; gTFA ~10–110 Credits; 50 RPS (Developer) ✓ | JSON-RPC, gRPC, Webhook |
| **Bitquery** (Pump.fun-API) | ~ `Transaction.Signer` (= `user`, nicht `creator`; Prereg-Definition braucht CreateEvent-Dekodierung) | ✓ `Block.Time` (Sekundenpräzision NV) | ✓ Raydium-Pfad; PumpSwap NV | Archiv ab Juni 2024 (NV) | Personal 49 USD, Scale 299 USD, Archiv-Packs ab 100 USD (alle NV) | Points (NV) | GraphQL, WebSocket, Kafka |
| **Eigener RPC / Yellowstone-Geyser** (Triton, QuickNode, Shyft, Chainstack) | ✓ Echtzeit, eigenes Decoding | slot ✓; Blockzeit aus `blocks_meta`/`blocks` (Tx-Updates nur slot) ✓ | ✓ Echtzeit | ✗ nur Replay ~100–3 000 Slots | Chainstack 49/149 USD, QuickNode 499 USD, Shyft ab 199 USD, Triton PAYG (alle NV) | NV | gRPC/protobuf |
| **Flipside** | NV | NV | NV | NV | Repos 2026-07-02 archiviert ✓; Datengeschäft an SonarX verkauft ~ | – | SQL (legacy) |
| **Old Faithful** (Triton, Solana-Archiv) | ✓ eigenes Decoding | ✓ | ✓ | ✓ ab Epoche 0 | Selbsthosting, 100e GB je Epoche (Gesamtarchiv vielfach größer); Preis NV | – | CAR, JSON-RPC, gRPC |
| **BigQuery** `crypto_solana_mainnet_us` | roh | ✓ roh | roh | evtl. seit 2025-03 nicht aktualisiert (NV) | Abfragekosten NV | – | SQL |
| **Substreams** (Pinax/StreamingFast) | ✓ Decoder vorhanden | ✓ Blockmodell | ✓ Decoder | NV | NV | NV | protobuf → Sinks |
| **Vybe** `/v4/trades` | ✗ nicht dokumentiert | ✓ `blockTime` | ✗ nicht dokumentiert | NV | Free-Tier ✓; 49/600 USD (NV) | 1 000 Zeilen/Seite ✓ | REST |
| Allium / Goldsky / Moralis / Solscan / Shyft-Indexer | NV | NV | NV | NV | Moralis 0/49/249/999 USD, Solscan 0/199/499/999 USD (Drittquelle) | NV | REST/SQL |
| **PumpPortal** Data-API | ✓ Echtzeit | ✓ Echtzeit | NV | ✗ keine Historie | kostenlos ✓ | NV | WebSocket |
| pump.fun Frontend-API (inoffiziell) | NV | NV | NV | NV | JWT nötig ✓ | Rate-Limit-Header ✓ | REST |

## 3. Einzelbewertungen (Belege)

### 3.1 Dune

- Spellbook-Modell `pumpdotfun_solana_base_trades` baut auf `solana.instruction_calls`; Create wird über den
  Instruktions-Diskriminator erkannt (`bytearray_substring(data,1,8) = 0x181ec828051c0777`, `account_arguments[1]` =
  mint, `[3]` = bonding_curve); Trades werden aus dem TradeEvent-Präfix `0xe445a52e51cb9a1dbddb7fd34ee661ee`
  geparst (sol_amount, token_amount, is_buy, user, trade_timestamp, Reserven); Spalten `block_time`,
  `block_slot`, `tx_index`; `project_start_date = '2024-01-14'`; **`fee_tier` ist hart auf 0,01 gesetzt**
  (veraltet seit den dynamischen Gebühren) [direkt geprüft] (Quelle:
  https://raw.githubusercontent.com/duneanalytics/spellbook/main/dbt_subprojects/solana/models/_sector/dex/pumpdotfun/solana/pumpdotfun_solana_base_trades.sql,
  abgerufen 2026-09-29).
- **Einschränkungen [direkt geprüft, Spellbook-SQL + idl/pump.json]:** Die Create-Erkennung prüft nur den
  Diskriminator der Instruktion `create` (`0x181ec828051c0777`); `create_v2` (`0xd6904cec5f8b31b4`, seit IDL-Commit
  2025-11-07, Pflicht für Mayhem/USDC/Holder-Rewards, im offiziellen pump.fun-Skill verwendet) wird nicht erfasst.
  Aus dem TradeEvent werden nur die virtuellen Reserven dekodiert (Offsets nach `timestamp`), keine realen Reserven
  und keine Fee-Felder; die Roh-Spalte `data` fehlt im finalen SELECT. Folge: Population, Creator, reale Reserven
  und Fees per eigener SQL über die Event-Diskriminatoren in `solana.instruction_calls` bilden.
- Weitere Modelle `pumpdotfun_solana_trades`, `pumpdotfun_version_1_base_trades` [direkt geprüft]
  (Quelle: .../pumpdotfun/solana/schema.yml, abgerufen 2026-09-29). Trader-Attribution für OKX-Routen im
  September 2026 korrigiert [direkt geprüft] (Quelle: https://github.com/duneanalytics/spellbook/pull/10036).
- Creator: nicht im Spellbook-Fragment; aus dem CreateEvent in `instruction_calls` mit derselben Technik
  decodierbar (eigene SQL). Complete: analog über den CompleteEvent-Diskriminator.
- Preise: [Drittquelle, "reconciled: false"] Free 0 USD, Plus ~390 USD, Premium ~1 990 USD (Quelle:
  https://raw.githubusercontent.com/api-evangelist/dune-analytics/main/plans/dune-analytics-plans-pricing.yml,
  abgerufen 2026-09-29). [Snippet, NV]: Free seit 2026-09-10 nur Lesezugriff für ältere Accounts;
  Analyst 75 USD (4 000 Credits), Plus 399 USD (25 000 Credits) (Quellen:
  https://www.kucoin.com/news/flash/dune-analytics-restricts-free-tier-to-view-only-access-from-september-10,
  https://costbench.com/software/onchain-analytics/dune-analytics/).
- Historientiefe der Solana-Rohtabellen: NV; Pump.fun-Modell ab 2024-01-14 ✓.

### 3.2 Helius

- Enhanced-Transactions-API: `PUMP_FUN` unter den bekannten Quellen; Responses mit `slot` und `timestamp`;
  `getTransactionsForAddress` mit slot-/blockTime-Filtern, Sortierung, Paginierung, ~10–110 Credits,
  "full" = 100 Txs/Call; Enhanced-API 100 Credits/Call [direkt geprüft] (Quelle:
  https://raw.githubusercontent.com/helius-labs/core-ai/main/helius-plugin/skills/build/references/enhanced-transactions.md,
  abgerufen 2026-09-29). Ob die Enhanced-API Pump.fun-Create/Complete typisiert: NV → eigenes Decoding.
- LaserStream (gRPC): nur Business+ (499 USD+), Replay bis 216 000 Slots (~24 h), 2 Credits je 0,1 MB
  [direkt geprüft] (Quelle: .../references/laserstream.md); SDK-README nennt 3 000 Slots Backfill
  (Widerspruch) [direkt geprüft] (https://github.com/helius-labs/laserstream-sdk).
- Pläne [direkt geprüft] (Quelle: .../references/onboarding.md): Agent 1 USDC (1 Mio. Credits, 10 RPS),
  Developer 49 USD (10 Mio., 50 RPS), Business 499 USD (100 Mio., 200 RPS), Professional 999 USD
  (200 Mio., 500 RPS); Zusatz-Credits 5 USD/Mio.; Credit-Kosten: 1 Standard-RPC, 10 gPA/DAS/"historical
  data", 100 Enhanced-API. Free 0 USD/1 Mio. Credits/10 RPS [Drittquelle]
  (https://raw.githubusercontent.com/api-evangelist/helius/main/plans/helius-plans-pricing.yml).
- Abgeleitet: ~1,1 Credits pro Transaktion im "full"-Modus. Für 1 200 Launches × erste Stunde (Annahme
  ≤ 500 Trades je Launch → ≤ 5 Seiten à 110 Credits) ≈ 660 000 Credits → passt in Developer (10 Mio.).
  Die Dev-Historie über 4 Monate (Millionen Creates) ist per RPC-Paging dagegen unpraktisch → Dune/Bitquery.

### 3.3 Bitquery

- Pump.fun-API-Beispiele: Create über `TokenSupplyUpdates` mit `Method: "create"`, liefert `Block.Time`,
  `Transaction.Signer` (= `user`/Signer, nicht der `creator` der Prereg-Definition) und Mint; Trades mit `Block.Time`, `Transaction.Signature`, Buy/Sell-Amounts,
  `Dex.ProtocolName = "pump"`; "Last Trade Before Graduation"-Query (Raydium-Pfad); `dataset: realtime`
  vs. Archiv/Combined [direkt geprüft] (Quelle: https://raw.githubusercontent.com/bitquery/Pump-Fun-API/main/README.md,
  abgerufen 2026-09-29). PumpSwap-Migration-Query: NV. Streaming via Kafka/Protobuf-Repos ✓.
- Archiv ab 1. Juni 2024, Self-Service nur Echtzeit, Archiv-Packs ab 100 USD/Monat: [Snippet, NV]
  (Quellen: https://docs.bitquery.io/docs/blockchain/Solana/historical-aggregate-data/,
  https://bitquery.io/products/pumpfun-api). Preise Developer free (1 000 Punkte), Personal 49 USD,
  Scale 299 USD: [Snippet, NV] (https://bitquery.io/blog/best-crypto-market-data-api).

### 3.4 Eigener RPC / Yellowstone-Geyser

- `SubscribeRequest.from_slot`, Filter `account_include/exclude/required`; Tx-Updates ohne Blockzeit
  (nur slot), Blockzeit über `blocks_meta` oder `blocks` [direkt geprüft] (Quelle:
  https://raw.githubusercontent.com/rpcpool/yellowstone-grpc/master/yellowstone-grpc-proto/proto/geyser.proto,
  abgerufen 2026-09-29). Replay ist Reconnect-Puffer, kein Backfill: Chainstack ~100 Slots [direkt geprüft]
  (https://github.com/chainstacklabs/grpc-geyser-tutorial); QuickNode 3 000 Slots, Shyft ~150 Slots [Snippet, NV].
- Backfill per `getSignaturesForAddress` (1–1 000 je Seite) [direkt geprüft]
  (https://raw.githubusercontent.com/solana-foundation/solana-com/main/apps/docs/content/docs/en/rpc/http/getsignaturesforaddress.mdx).
- Fazit: für Echtzeit-Bots gedacht (nicht Ziel von Edge Lab); für den historischen Backtest ungeeignet.

### 3.5 Flipside

- `FlipsideCrypto/sdk` und `gitbook` am 2026-07-02 archiviert [direkt geprüft]
  (https://github.com/FlipsideCrypto/sdk, https://github.com/FlipsideCrypto/gitbook). Datengeschäft im
  Mai 2026 an SonarX verkauft [Drittquelle] (https://github.com/api-evangelist/flipside). → nicht empfohlen.

### 3.6 Archive und weitere

- Old Faithful: vollständige Historie ab Epoche 0 als CAR-Dateien, JSON-RPC/gRPC-Server, `getBlock`,
  `getTransaction`, `getSignaturesForAddress` [direkt geprüft] (https://github.com/rpcpool/yellowstone-faithful);
  "100s of GB" **je Epoche** (README: "To avoid fetching the full dataset for an epoch (100s of GB)"), Gesamtarchiv
  entsprechend vielfach größer; Selbsthosting – zu aufwendig für EXP002.
- BigQuery `crypto_solana_mainnet_us` (Rohdaten) [direkt geprüft] (https://raw.githubusercontent.com/blockchain-etl/public-datasets/master/README.md);
  seit 2025-03 evtl. stale [Snippet, NV].
- Substreams: Pump.fun-Decoder (Bonding Curve, PumpSwap) vorhanden [direkt geprüft]
  (https://github.com/pinax-network/substreams-solana-idls); Preise NV.
- Vybe `/v4/trades` (programAddress-Filter, `timeStart/timeEnd`, `limit` ≤ 1 000, `blockTime`) mit Free-Tier
  [direkt geprüft] (https://github.com/vybenetwork/solana-historical-trade-data-api); keine Create/Complete.
- Moralis-Pläne 0/49/249/999 USD [Drittquelle, "reconciled: true"] (https://raw.githubusercontent.com/api-evangelist/moralis/main/plans/moralis-plans-pricing.yml);
  Pump.fun-Endpoints NV. Solscan Pro 0/199/499/999 USD [Drittquelle] (https://raw.githubusercontent.com/api-evangelist/solscan/main/plans/solscan-plans-pricing.yml).
- PumpPortal: Data-API kostenlos, Echtzeit-WebSocket (`subscribeNewToken`, `subscribeTokenTrade`)
  [direkt geprüft] (https://github.com/thetateman/Trading-API); keine Historie.
- pump.fun Frontend-API v3 (inoffiziell, JWT) [direkt geprüft] (https://github.com/BankkRoll/pumpfun-apis).

## 4. Empfehlung (Preis-Leistung, kein Kauf)

1. **Primär: Dune** – einzige geprüfte Quelle, die Pump.fun-Events per SQL (eigene Abfragen über die
   Event-Diskriminatoren in `solana.instruction_calls`, weil das Spellbook nur `create` und nur virtuelle Reserven
   dekodiert), `block_time`/`block_slot`/`tx_index` und eine Historie ab 2024-01-14 liefert und CSV-Export
   erlaubt. Damit lassen sich Dev-Historie (Millionen Creates), Basisrate, Matching-Pool und die
   Trades der ausgewählten ~1 200 Launches in wenigen Abfragen ziehen. Fees **nicht** aus `fee_tier`
   (hart 0,01), sondern aus den Event-Feldern decodieren. Kosten: Analyst 75 USD/Monat bis Plus 399 USD/Monat
   (beide NV; abhängig vom Export-Volumen und davon, ob der Free-Tier noch Abfragen erlaubt).
2. **Sekundär: Helius Developer (49 USD/Monat, 10 Mio. Credits [direkt geprüft])** – Roh-Transaktionen
   für die Simulator-Validierung (Fee-Felder, u64-Rekonstruktion, (slot, tx_index)-Ordnung) und als Fallback
   für die Trade-Details der ausgewählten Launches (~0,7 Mio. Credits).
3. **Geschätzte Monatskosten für 1–2 Monate: ca. 124–448 USD/Monat** (75–399 USD Dune + 49 USD Helius).
   Günstigste Variante bei bestätigtem Dune-Free-Zugang: 49 USD/Monat.
4. Nicht empfohlen: Geyser/eigener RPC (nur Echtzeit), Flipside (eingestellt), Old Faithful (Aufwand),
   Bitquery nur als Ersatz für Dune, falls dessen Preise/Free-Tier nach Direktprüfung ungünstiger sind.

Offen: OQ-007 (Preise direkt prüfen), OQ-020 (Datenquelle in der Prereg fixieren), OQ-012/OQ-023
(Fee-Felder und Programmänderungen 2026 im Decoder berücksichtigen).

## 5. Quellenverzeichnis (abgerufen 2026-09-29)

Direkt geprüft (GitHub/PyPI): pump-fun/pump-public-docs (docs/PUMP_PROGRAM_README.md, FEE_PROGRAM_README.md,
fees.png, idl/), sevenlabs-hq/carbon (pumpfun-decoder, pump-swap-decoder, pump-fees-decoder),
rckprtr/pumpdotfun-sdk (Legacy-IDL), helius-labs/core-ai (enhanced-transactions.md, laserstream.md,
webhooks.md, onboarding.md, priority-fees.md), helius-labs/laserstream-sdk, solana-foundation/solana-com
(getsignaturesforaddress.mdx, getblocktime.mdx, fee-structure.mdx, compute-budget.mdx),
rpcpool/yellowstone-grpc, rpcpool/yellowstone-faithful, chainstacklabs/grpc-geyser-tutorial,
chainstacklabs/pump-fun-bot, bitquery/Pump-Fun-API, duneanalytics/spellbook (pumpdotfun-Modelle,
PR #10036), FlipsideCrypto/sdk, FlipsideCrypto/gitbook, blockchain-etl/public-datasets,
pinax-network/substreams-solana-idls, streamingfast/substreams-solana,
vybenetwork/solana-historical-trade-data-api, thetateman/Trading-API, BankkRoll/pumpfun-apis,
api-evangelist/{helius,bitquery,dune-analytics,flipside,moralis,solscan}.

Nur Snippet (Seiten gesperrt): helius.dev/pricing, docs.bitquery.io (historical-aggregate-data,
pump-fun-to-pump-swap), bitquery.io/pricing, dune.com/pricing, kucoin.com/news (Dune Free-Tier),
costbench.com (Dune-Pläne), chainstack.com (Yellowstone-Preise), quicknode.com (gRPC), shyft.to (Preise),
triton.one/pricing, docs.allium.so, docs.goldsky.com, docs.moralis.com (Pump.fun-API), pumpportal.fun,
discuss.google.dev (BigQuery-Dataset), arxiv.org/html/2602.14860v1, zenodo.org/records/21383616.
