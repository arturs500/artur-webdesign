# OPEN_QUESTIONS – Edge Lab

Regel: Unklarheiten werden hier notiert statt geraten. Jede Frage hat eine ID, einen Default (falls
unentschieden) und die Angabe, welchen Freeze sie blockiert. Prereg-Dokumente verweisen nur auf IDs.

Legende Kennzeichnung von Fakten in allen Edge-Lab-Dokumenten:

- **[direkt geprüft]** – Seite/Datei wurde am Abrufdatum tatsächlich geladen (z. B. PyPI-JSON, GitHub-Raw).
- **[Snippet]** – nur als WebSearch-Snippet der genannten offiziellen URL gesehen; die Seite selbst war
  wegen der Netzwerk-Policy der Arbeitsumgebung nicht abrufbar (siehe OQ-007).
- **NICHT VERIFIZIERT** – auf keiner abrufbaren Quelle bestätigt.

Status-Werte: `offen`, `entschieden`, `geschlossen`.

---

## OQ-001 – PREREGISTRATION_EXP001.md v0.3 fehlt im Repository

- Datum: 2026-09-29
- Kontext: Auftrag Phase A, Schritt 1 ("Lies PREREGISTRATION_EXP001.md komplett").
- Befund: Die Datei existiert weder im Arbeitsbaum noch in einem Branch oder Commit von
  `arturs500/artur-webdesign` (geprüft: `git log --all --diff-filter=A`, alle Remote-Branches,
  GitHub-Code-Suche, geschlossener PR #1). Kein anderes Repository des Nutzers enthält sie.
- Frage: Wo liegt die Prereg v0.3? Lokal, in einem Chat oder noch nicht geschrieben?
- Optionen: (a) Nutzer pusht die Datei auf den Branch; (b) Nutzer fügt den Inhalt als Nachricht ein;
  (c) Datei liegt in einem anderen Repo (Owner/Repo nennen).
- Default: Weiterarbeiten ohne Datei; keine Hypothese, Metrik, Schwelle oder PASS/FAIL-Regel erfinden.
- Blockiert: **EXP001-Freeze** (ohne Datei kein Freeze, kein Hash).
- Status: `entschieden` (2026-09-29, Nutzer: "Ohne Datei weiterarbeiten"); Datei nachliefern bleibt offen.

## OQ-002 – Anhang A: Discovery-Kriterium A.1 muss mit dem Prereg-Text abgeglichen werden

- Datum: 2026-09-29
- Kontext: `scripts/channel_discovery.py`, Anhang A der Prereg (nicht einsehbar, siehe OQ-001).
- Gewähltes Default-Kriterium A.1 (Nutzerentscheidung 2026-09-29): Suche über eine feste Keyword-Liste
  mit `contacts.search`, nur Broadcast-Kanäle (keine Gruppen/Megagroups), Ranking nach
  `participants_count` absteigend (Tiebreak `channel_id` aufsteigend), Filter: mindestens ein Post ab Stichtag
  00:00 UTC minus 7 Tage bis zum Abrufzeitpunkt (der Lauf erfolgt am Stichtag selbst), Top-50.
- Frage: Deckt sich A.1 mit dem Kriterium in Anhang A der Prereg (Keyword-Liste, Aktivitätsfenster,
  Sprache/Region, Ausschlüsse)?
- Zusatzentscheidung: `contacts.search` bietet in TL-Layer 229 die Flags `broadcasts` und `bots` (Telethon 1.45.0:
  `SearchRequest(q, limit, broadcasts=None, bots=None)` [direkt geprüft per Introspektion]). Die Server-Semantik ist
  NICHT VERIFIZIERT (core.telegram.org gesperrt). Default: Flag nicht gesetzt; bei Übernahme (`broadcasts=True`)
  wird `CRITERION_VERSION` auf A.2 angehoben und das Flag in den Kriterium-Hash aufgenommen.
- Default: A.1 wie im Skript kodiert; Keyword-Liste und Parameter sind Teil des Kriteriums.
- Blockiert: **EXP001-Freeze**.
- Status: `offen`.

## OQ-003 – Discovery: Umgang mit Scam-/Fake-/Restricted-Flags und fehlender Abonnentenzahl

- Datum: 2026-09-29
- Kontext: `scripts/channel_discovery.py`; `channelFull.participants_count` ist ein optionales Feld
  [direkt geprüft: Flag-Feld des Typs `channelFull` in https://raw.githubusercontent.com/gotd/td/main/tg/tl_chat_full_gen.go;
  Telethon 1.45.0 `types.ChannelFull.participants_count: Optional[int] = None`].
- Frage: Sollen Kanäle mit Telegram-Flag `scam`/`fake` oder `restricted` aus den Top-50 ausgeschlossen
  werden? Wie werden Kanäle ohne `participants_count` gerankt?
- Default: Flags werden nur protokolliert (Spalten in der CSV), nicht gefiltert; Kanäle ohne
  `participants_count` landen am Ende des Rankings und werden gezählt (meta.json).
- Blockiert: **EXP001-Freeze**.
- Status: `offen`.

## OQ-004 – EXP001: Baseline-Definition und Horizonte für die Birdeye-CU-Rechnung

- Datum: 2026-09-29
- Kontext: `docs/birdeye_endpoints.md`, Abschnitt CU-Bedarf.
- Bekannt aus dem Auftrag: mindestens 200 Events, Primärhorizont 1 h, "inkl. Baselines".
- Unbekannt: Art der Baseline (zeitversetzte Fenster desselben Tokens vs. k gematchte Zufalls-Token),
  Anzahl k, Pre-Window, weitere Horizonte (4 h, 24 h?), Kerzenintervall (1m?).
- Default: Rechnung als Sensitivitätstabelle über k in (0, 1, 3, 5), Horizont in (1 h, 4 h, 24 h),
  Pre-Window 60 min, 1m-Kerzen.
- Blockiert: **EXP001-Freeze** (Plan-Dimensionierung), nicht die Hypothese.
- Status: `offen`.

## OQ-005 – Birdeye: CU-Kosten pro OHLCV-Call, Historientiefe je Plan, Abdeckung der Pump.fun-Kurve

- Datum: 2026-09-29
- Kontext: `docs/birdeye_endpoints.md`.
- Befund: Die offizielle CU-Tabelle war nicht abrufbar (OQ-007); der OHLCV-Wert ist **NICHT VERIFIZIERT**
  (Drittanbieter nennt 40 CU/Call). Historische Datentiefe je Plan: NICHT VERIFIZIERT. Ob Birdeye-OHLCV
  Trades auf der Pump.fun-Bonding-Curve (vor Graduation) abdeckt, ist ungeprüft; für Telegram-Calls auf
  frische Pump.fun-Token entscheidet das über die Eignung der Datenquelle.
- Default: Sensitivitätsrechnung mit 40/100/200 CU pro Call; vor dem Freeze mit dem Free-Tier einen
  Pilot (ca. 20 Events) fahren und den Verbrauch über den Credits-Usage-Endpoint messen.
- Blockiert: **EXP001-Freeze**, falls die Prereg Birdeye als Datenquelle festschreibt.
- Status: `offen`.

## OQ-006 – Birdeye: Plan-Entscheidung (nur Empfehlung, kein Kauf)

- Datum: 2026-09-29
- Kontext: `docs/birdeye_endpoints.md`, Abschnitt Empfehlung.
- Empfehlung: Lite (39 USD/Monat, 2,5 Mio. CU, 15 rps) [Snippet] für einen Monat; Free/Standard nur für
  den Pilot; x402 Pay-per-Request (0,003 USD/Request) [Snippet] als Alternative ohne Abo, Historientiefe
  dort NICHT VERIFIZIERT.
- Frage: Kauf-Freigabe? (Nicht Teil dieses Auftrags.)
- Blockiert: keinen Freeze (Datenabruf erfolgt nach dem Freeze).
- Status: `offen`.

## OQ-007 – Direktverifikation der Quellen nach Freigabe der gesperrten Hosts

- Datum: 2026-09-29
- Kontext: Alle Edge-Lab-Dokumente. Die Netzwerk-Policy der Cloud-Arbeitsumgebung blockierte am
  2026-09-29 den Direktabruf folgender Hosts (curl über den Proxy, kein Verbindungsaufbau):
  `docs.birdeye.so`, `bds.birdeye.so`, `public-api.birdeye.so`, `birdeye.so`, `docs.helius.dev`,
  `www.helius.dev`, `docs.bitquery.io`, `bitquery.io`, `dune.com`, `docs.dune.com`,
  `flipsidecrypto.xyz`, `core.telegram.org`, `my.telegram.org`, `docs.telethon.dev`, `codeberg.org`,
  `solana.com`, `docs.jito.wtf`, `pump.fun`, `quicknode.com`, `triton.one`, `shyft.to`,
  `chainstack.com`, `api.tgstat.ru`, `telemetr.io` sowie News-/Paper-Seiten (theblock.co, coindesk.com,
  arxiv.org, zenodo.org), außerdem `skills.lc`, `data.birdeye.so`, `bds-support.birdeye.so`, `allium.so`,
  `goldsky.com`, `moralis.com`, `pumpportal.fun`. Erreichbar waren `pypi.org`, `raw.githubusercontent.com`,
  `github.com` (Seiten und Raw; `api.github.com` liefert 403), `pkg.go.dev`, `registry.npmjs.org`. Diese Liste
  ist die kanonische Host-Liste für alle Edge-Lab-Dokumente.
- Frage: Sollen die Hosts in den Environment-Einstellungen freigegeben werden, damit alle
  [Snippet]-Angaben (v. a. Preise, CU-Tabelle, Rate-Limits) direkt geprüft werden können?
- Default: Kennzeichnung beibehalten; vor einer Kaufentscheidung oder einem Freeze, der auf einer
  [Snippet]-Zahl beruht, die betreffende Seite direkt prüfen.
- Blockiert: EXP001-Freeze nur, soweit die Prereg auf diesen Zahlen aufbaut; sonst keinen.
- Status: `offen`.

## OQ-008 – Ablage der Edge-Lab-Dateien im Website-Repository (GitHub Pages / Jekyll)

- Datum: 2026-09-29
- Kontext: Das Repository ist die GitHub-Pages-Website (CNAME, index.html im Root). Es gibt kein
  `.nojekyll` und keine `_config.yml`. Nach einem Merge nach `main` würden `.md`-Dateien von Jekyll als
  HTML unter der Kundendomain ausgeliefert; Liquid-Syntax in Markdown kann den Pages-Build brechen.
- Frage: Eigenes Repository für Edge Lab, `_config.yml` mit `exclude`, oder `.nojekyll`?
- Default: Feature-Branch bleibt bis zur Entscheidung ungemergt; in allen Edge-Lab-Markdown-Dateien wird
  keine Liquid-Syntax verwendet. Pfade wurden wie vom Nutzer vorgegeben angelegt (Repo-Root).
- Blockiert: keinen Freeze (Freeze-Commit kann auf dem Branch erfolgen), aber den Merge.
- Status: `offen`.

## OQ-009 – EXP002: Analysefenster D0/D1 und rollierender Lookback L

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Abschnitte Population und Dev-Historie.
- Frage: Konkrete Kalenderdaten des Analysefensters und Länge des Lookbacks je Event.
- Default: 30 zusammenhängende Tage; L = 90 Tage; Datenbedarf = Fenster + L + 7 Tage Reifung.
  Fensterlänge vorab per reiner Zählung der Treatment-Events dimensionieren (erlaubter Vorab-Schritt).
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-010 – EXP002: Parameter der Treatment-Regel

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Treatment-Definition.
- Default: gereifte Vor-Launches (Create mindestens 7 Tage vor dem Entscheidungszeitpunkt),
  `n_prev >= 10`, `grad_prev >= 2`, `grad_prev / n_prev >= 0,10`. Hinweis: Bei `n_prev = 10` wirkt
  `grad_prev >= 2` als 20-%-Schwelle (ein Treffer reicht nicht); ab `n_prev >= 11` ist die Bedingung durch die
  10-%-Regel impliziert (effektive Mindestquote `2 / n_prev`).
- Alternative: Relativ-Regel (Wilson-Untergrenze der Dev-Quote > Basisrate des Vorzeitraums) – nur als
  sekundäre Analyse.
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-011 – EXP002: Ordergröße S, Exit-Horizonte, Primärkombination

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Simulation.
- Default: S = 0,5 SOL (Sensitivität 0,1 und 1,0 SOL); Exit primär +5 min nach Entry, sekundär +15 min
  und +60 min; Primärtest = Entry T+30 s mit Exit +5 min; T+5 s als optimistische Grenze gekennzeichnet.
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-012 – EXP002: Fee-Modell (protokollierte Fee-Felder vs. Tabelle; 1,25 % ist zeitabhängig)

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Kostenmodell; `docs/exp002_data_sources.md`.
- Befund: Die offizielle Gebührentabelle (fees.png im Repo pump-fun/pump-public-docs) nennt für die
  Bonding Curve 0,30 % Creator + 0,95 % Protokoll = 1,25 % [direkt geprüft]; die Annahme aus PR #1
  (holder-scorer) ist damit bestätigt, gilt aber erst seit Einführung der dynamischen Gebühren
  (Datum laut Doku "Monday, September 1, 20:00 UTC", Jahr aus dem Wochentag abgeleitet: 2025). Davor
  galt die Legacy-Gebühr von 100 bps. Das TradeEvent führt die tatsächlich gezahlten Fee-Felder mit. fees.png ist
  ein Snapshot (Commit "Publish fee program README", 2025-08-29); maßgeblich sind die On-chain-Tiers im
  `FeeConfig`-Account (`fee_tiers`, `stable_fee_tiers`, `exotic_flat_fees`) [direkt geprüft: idl/pump_fees.json];
  beim Freeze per RPC auslesen und Slot dokumentieren.
- Default: Fees je Trade aus den Event-Feldern (`fee_basis_points`, `fee`, `creator_fee_basis_points`,
  `creator_fee`); Fallback zeitindexierte Tabelle. Kein konstanter Satz.
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-013 – EXP002: Priority-Fee-Szenarien, ATA-Rent, Jito-Tip

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Kostenmodell.
- Default: drei Szenarien für den Compute-Unit-Preis (low 10 000 / medium 120 000 / high 500 000
  µLamports pro CU, Beispielwerte aus der Helius-Priority-Fee-Doku [direkt geprüft]) bei 120 000 CU pro
  Buy/Sell (Default des offiziellen pump.fun-Skills, swap/SKILL.md [direkt geprüft]; die pump.fun-FAQ nennt
  100 000 [direkt geprüft] → Sensitivität); primär medium. Jito-Tip optional 0,0001 SOL (Default im
  pump.fun-Skill [direkt geprüft]). ATA-Rent: Wert am Stichtag per
  `getMinimumBalanceForRentExemption(165)` abfragen – **NICHT VERIFIZIERT** (Größenordnung 0,002 SOL); 165 Byte =
  `Account::LEN` des SPL-Token-Programms [direkt geprüft: solana-program/token, interface/src/state.rs].
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-014 – EXP002: Replay vs. Overlay für den eigenen Preiseinfluss; Slippage-Limit

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Simulation.
- Default: (a) Replay der realen Folge-Trades mit gleichen Inputs nach dem eigenen Buy = primär;
  (b) Overlay (realer Zustand bei Exit plus eigenes Delta) = Sensitivität. Primär kein Slippage-Limit
  (Fill immer); sekundär Limit 10 % (kein Fill = nur Gebühren).
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-015 – EXP002: Behandlung einer Graduation vor dem Exit

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Exit-Regeln.
- Default: Doppelbehandlung – (a) optimistisch: Verkauf zum Kurvenzustand unmittelbar vor dem Trade,
  der `complete = true` setzt, abzüglich Fees; (b) konservativ: Position bis zum Exit-Zeitpunkt nicht
  handelbar, Bewertung 0 (Totalverlust). PASS nur, wenn der Primärtest unter beiden Varianten besteht.
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-016 – EXP002: Matching-Strata, k, Fallback-Hierarchie, Seed

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Baseline.
- Default: Strata = 6-h-UTC-Block × Mcap-Bin (Bin 0 = kein Self-Buy; Bins 1–5 = Quintile des
  Self-Buy-Betrags innerhalb der Self-Buy-Teilpopulation); k = 5 ohne Zurücklegen; Fallback:
  alle verfügbaren Kontrollen → Nachbar-Bin → angrenzender Block → bei weniger als 2 Kontrollen
  Ausschluss aus der gepaarten Analyse; Seed wird beim Freeze fixiert.
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-017 – EXP002: Cap N pro Dev, Fensterverlängerung, Datenqualitäts-Stopp

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Statistik und PASS/FAIL.
- Default: maximal 20 Events pro Dev (Zufallsauswahl mit festem Seed), Robustheit ungedeckelt und
  dev-gleichgewichtet; bei Underpower einmalige Verlängerung des Fensters um 50 % nach hinten (frühere
  Daten); mehr als 5 % ausgeschlossene Events → "nicht testbar (Datenqualität)".
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-018 – Dev-Identität = Creator-Wallet; gebündelte Fremd-Wallets

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Limitationen.
- Befund: Ein Dev, der Wallets wechselt, erscheint als neuer Dev (n_prev = 0) und landet im
  Kontrollpool (Verdünnung, Bias Richtung Null = konservativ). Käufe über Fremd-Wallets im Create-Slot
  sind vom Creator-Self-Buy nicht unterscheidbar.
- Default: In EXP002 keine Wallet-Clusterung; als Kandidat für EXP003 vormerken.
- Blockiert: keinen Freeze.
- Status: `offen`.

## OQ-019 – Graduation-Basisrate: Quellen widersprechen sich (ca. 0,2 % bis 2,7 %)

- Datum: 2026-09-29
- Kontext: Auftrag Phase B, Punkt 7; `PREREGISTRATION_EXP002.md`.
- Befund: Berichtete Werte reichen von 0,198 % (2026-05-08 bis 2026-06-10, Zenodo 21383616, Snippet) über 0,63 %
  (Sept. 2025, arXiv 2602.14860v1, Snippet), 1,15 % (Anfang 2026), 1,4 % (Jan. 2025) bis 2,7 % (j.tools) und
  kurzfristig 4,7–6,7 %
  nach der BOOST-Änderung (Juli 2026). Alle Werte **NICHT VERIFIZIERT** (nur Snippets, Seiten gesperrt);
  Definitionen und Zeiträume unterscheiden sich.
- Entscheidung: Die Basisrate wird **nicht übernommen**, sondern aus den eigenen Daten gemessen:
  Anteil der Launches mit `complete` innerhalb von 7 Tagen nach Create, Wilson-95%-CI, ausschließlich
  aus dem Zeitraum vor dem Analysefenster (point-in-time), im Fenster nur deskriptiv.
- Blockiert: **EXP002-Freeze** (Messvorschrift muss in der Prereg stehen – ist als Default enthalten).
- Status: `entschieden` (Messen statt übernehmen), Zahl selbst offen.

## OQ-020 – EXP002: Datenquelle – Dune-Preise/Free-Tier unverifiziert, Helius als Zweitquelle

- Datum: 2026-09-29
- Kontext: `docs/exp002_data_sources.md`.
- Befund: Dune-Spellbook liefert Create-Erkennung und TradeEvent-Felder inkl. Reserven, block_time,
  block_slot, tx_index seit 2024-01-14 [direkt geprüft, SQL im GitHub-Repo]. Preise nur aus Drittquelle/
  Snippet (Free evtl. seit 2026-09-10 nur Lesezugriff; Analyst 75 USD; Plus 399 USD) – NICHT VERIFIZIERT.
  Helius Developer 49 USD/Monat, 10 Mio. Credits [direkt geprüft, helius-labs/core-ai].
- Frage: Kauf-Freigabe und Bestätigung der Preise nach Host-Freigabe (OQ-007).
- Default: Empfehlung Dune (primär) + Helius Developer (Validierung/Fallback); nichts kaufen.
- Blockiert: **EXP002-Freeze** (Datenquelle muss in der Prereg stehen).
- Status: `offen`.

## OQ-021 – Telegram: Account-/ToS-Risiko, Telethon-Pin, Coverage von contacts.search

- Datum: 2026-09-29
- Kontext: `scripts/channel_discovery.py`, `scripts/README_channel_discovery.md`.
- Befund: `contacts.search` ist nur für User-Accounts nutzbar und liefert pro Query nur wenige Treffer
  (Telethon-Issue #1431 [direkt geprüft]); Ergebnisse sind zeitlich instabil → Discovery ist ein
  Snapshot am Stichtag (CSV + meta.json + SHA-256). Telegram-ToS verbieten Flooding/Spam; Drittanbieter-
  Bibliotheken können zu Account-Beschränkungen führen (Telethon-FAQ [direkt geprüft]).
- Default: Telethon 1.45.0 gepinnt; etablierter Account (kein neuer, keine VoIP-Nummer); kleines
  Request-Budget; keine Joins; Session-Datei außerhalb des Repos.
- Blockiert: keinen Freeze.
- Status: `offen`.

## OQ-022 – No-Peek: Vorkenntnisse aus PR #1 (holder-scorer) dokumentieren

- Datum: 2026-09-29
- Kontext: Beide Preregs.
- Befund: Die Vorgänger-Session (geschlossener PR #1) hat ein Pump.fun-Bewertungswerkzeug inkl.
  Papier-Trading entworfen; laut PR-Text waren RPCs aus der Umgebung nicht erreichbar, es wurden also
  keine realen Marktdaten ausgewertet. Diese Vorkenntnis ist in der No-Peek-Erklärung von EXP002
  offenzulegen.
- Default: Erklärung in `PREREGISTRATION_EXP002.md`, Abschnitt No-Peek.
- Blockiert: **EXP002-Freeze** (Erklärung muss vollständig sein).
- Status: `offen`.

## OQ-023 – Pump.fun-Programmänderungen 2026: Filterregeln für EXP002

- Datum: 2026-09-29
- Kontext: `PREREGISTRATION_EXP002.md`, Population.
- Befund [direkt geprüft: Commit-Historie idl/pump.json in pump-fun/pump-public-docs, abgerufen 2026-09-29]:
  Mayhem-Mode und `create_v2` (IDL 2025-11-07), Cashback-Update (2026-02-17), USDC-quotierte Coins
  (`virtual_sol_reserves` → `virtual_quote_reserves`, 2026-05-07), **Holder-Rewards** (2026-09-12: bei
  `is_holder_reward = true` setzt das Programm als `creator` eine PDA je Mint; Cashback deprecated). Negative
  virtuelle Quote-Reserven betreffen nur PumpSwap-Pools (docs/NEGATIVE_VIRTUAL_QUOTE_RESERVES.md), nicht die
  Bonding Curve. Buyback-Felder: kein datierbarer Commit (NICHT VERIFIZIERT). Das Dune-Spellbook erkennt nur
  `create`, nicht `create_v2` (siehe docs/exp002_data_sources.md).
- Frage: Dev-Identität bei Holder-Rewards-Coins (`user` als Dev vs. Ausschluss); Umgang mit `create_v2`.
- Default: Nur Launches mit SOL als Quote-Mint; Population über den CreateEvent-Diskriminator (deckt `create` und
  `create_v2`); Dev = `creator`, bei `is_holder_reward = true` Dev = `user` (Signer), Sensitivität ohne
  Holder-Rewards-Coins; Kurvenparameter je Coin aus dem CreateEvent lesen, nicht aus Konstanten; Mayhem-Coins
  als Flag mitführen und in einer Sensitivität ausschließen; `idl/pump.json` beim Freeze pinnen (SHA-256).
- Blockiert: **EXP002-Freeze**.
- Status: `offen`.

## OQ-024 – Sniper (holder-scorer): die bisherigen Calls liegen nicht vor

- Datum: 2026-09-29
- Kontext: `docs/sniper_review.md`; Nutzerwunsch, die bisherigen Calls des Sniper zu prüfen ("was falsch war").
- Befund: Im Repo gibt es keine Aufzeichnungen (`live.jsonl`, `papier.jsonl`, `beobachtungen.jsonl`), keine
  Telegram-Exporte und keine Liste der gesendeten Calls. Laut PR-#1-Text waren RPC/Telegram aus der
  Entwicklungsumgebung nicht erreichbar; ob das Werkzeug beim Nutzer lief, ist unbekannt. Geprüft werden konnten
  deshalb nur Code, Regeln und Datenpfad, nicht die realen Alarme.
- Frage: Existieren Aufzeichnungen? Wenn ja: Dateien in `data/sniper/` ablegen (JSONL wie vom Werkzeug
  geschrieben) oder eine Liste `mint, Unix-Zeit des Calls, Alarmstufe` liefern.
- Default: Nachrechnung erst mit Daten; Werkzeug ab jetzt mit `--record` und `--tape` betreiben, damit jeder
  Alarm später mit Slot, Kurvenstand und Regelversion objektiv nachgerechnet werden kann.
- Blockiert: keinen Freeze; blockiert die Auswertung "was war falsch" für die Vergangenheit.
- Status: `offen`.

## OQ-025 – Sniper-Betrieb für Handy-Alarme: Einordnung, Stufe, Budget

- Datum: 2026-09-29
- Kontext: `docs/sniper_review.md`, `tools/holder-scorer/README.md`.
- Einordnung: Das Werkzeug enthält keinen Trading-Code (geprüft per Suche nach sendTransaction/Keypair/sign);
  Alarme aufs Handy sind Beobachtungen einer Call-Quelle unter Test, keine Kaufsignale. Damit bleibt der
  Betrieb mit der Regel Edge-First vereinbar, solange kein Kapital folgt.
- Offene Entscheidungen: (a) Stufe 1 mit `--tiers go,widerruf,rug` (Modell laut README: ca. 20 GO je Stunde)
  statt Stufe 2 (ca. 170 Nachrichten je Stunde, für ein Handy unbrauchbar); (b) `--budget 1000` je Stunde, damit
  das kostenlose Helius-Kontingent (1 Mio. Credits je Monat [direkt geprüft, helius-labs/core-ai]) nicht nach
  etwa zehn Tagen leer ist (Standard 4000 je Stunde ≈ 2,9 Mio. je Monat); die Websocket-Kosten "20 Credits je MB"
  aus dem README sind NICHT VERIFIZIERT; (c) Papier-Latenz 30 s als Standard, weil ein Mensch nach Telegram-Push
  frühestens 45–100 s nach dem Launch handeln könnte, nicht 2 s.
- Default: (a) Stufe 1, (b) Budget 1000, (c) Latenz 30 s – wie im README-Startbefehl.
- Blockiert: keinen Freeze.
- Status: `offen`.

## OQ-026 – Sniper: Erfolgsmaß und Vorregistrierung (EXP003-Kandidat)

- Datum: 2026-09-29
- Kontext: `docs/sniper_review.md`, Abschnitt Umbau-Plan.
- Befund: `outcome`/`evaluate` messen "Holder-Zahl ×1,5 nach 15 Minuten" zum Prüfzeitpunkt statt Netto-Rendite;
  der Papier-Report wählt die beste von 64 Regeln bzw. 12 Strategien ohne Korrektur. Beides kann Verluste als
  Treffer zählen.
- Frage: Soll "Sniper-Alarme als Call-Quelle" als EXP003 vorregistriert werden (Hypothese, Kontrollgruppe,
  Latenz 30 s, Rendite aus Tape und Kurvenmathematik, Wilson-/Bootstrap-CI, PASS/FAIL vorab)?
- Stand 2026-10-01: Der Rechenweg existiert (`tape report`, Modul `replay.py`: Rendite-Label, Kontrollgruppe über
  `--tape-sample`, Block-Bootstrap, Holm, Primärzeile GO/+30 s/+300 s). Offen bleiben die Prereg selbst (Fenster,
  Mindeststichprobe ≥ 200 Alarme aus ≥ 30 Stunden, PASS/FAIL-Text), das Matching nach Kurvenfortschritt/Self-Buy
  und der Replay der Folge-Trades statt Overlay (P1). Die Token-Account-Einlage (2 039 280 Lamports) ist eine
  Annahme und per RPC zu prüfen.
- Default: Ja, nach zwei bis vier Wochen Aufzeichnung mit `--record`/`--tape --tape-sample 0.1`; bis dahin keine
  Kaufentscheidung aus Alarmen ableiten.
- Blockiert: keinen Freeze.
- Status: `offen`.

## OQ-027 – Sniper: Präzisions-Gate (Halter-Anstieg, Profil-Ähnlichkeit) – Schwellen und Label ohne Daten gesetzt

- Datum: 2026-10-02
- Kontext: `tools/holder-scorer/holder_scorer/profile.py`, `docs/sniper_review.md` Abschnitt 4.1; Nutzerwunsch
  "Coins, die in Sekunden steigende Halterzahlen haben und den gespeicherten guten Coins gleichen".
- Befund: Es liegen keine Aufzeichnungen vor (OQ-024), also auch keine gespeicherten guten Coins. Das Gate ist
  deshalb als Mechanismus gebaut, der aus den eigenen Dateien lernt (`profil bauen`), und mit Startwerten belegt,
  die nicht aus Daten stammen: Halter-Anstieg ≥ 2 (Stufe 1: ≥ 3) je 15 s; Ähnlichkeit ≥ 0,7; Band 10.–90.
  Perzentil; Label "gut = graduiert oder Netto-Rendite > 0 bei Einstieg t0+60 s, Ausstieg +180 s, 0,08 SOL,
  Priority medium"; Checkpoints 10/20/30/45 s; mindestens 5 gute Coins je Checkpoint.
- Fragen: (a) Welche Halter-Anstiegsschwelle trennt Rendite bei gleichem Momentum (Test wie Umbau-Plan Punkt 14)?
  (b) Ist "graduiert" als gut zu zählen, obwohl `tape report` eine Graduation vor dem Ausstieg konservativ als 0
  rechnet (kein PumpSwap-Kurs im Tape)? (c) Wie mit korrelierten Merkmalen umgehen (Zufluss, Zufluss der letzten
  15 s, Kaufgröße zählen dreifach)? (d) Soll ein nach BLICK vom Profil blockiertes GO einen WIDERRUF auslösen?
  (e) Mint-Liste per RPC: welche Coins gelten als Referenz (nur graduierte? aus welchem Zeitraum?), und wie hoch
  ist der reale Credit-Verbrauch je Coin (Schätzung: Signatur-Seiten + getTransaction je Trade im Fenster;
  NICHT VERIFIZIERT)?
- Optionen: Profil erst nutzen, wenn `--split 0.5` ein Bootstrap-Intervall > 0 zeigt (Pro: keine Lärmfilter;
  Contra: dauert Tage) vs. sofort mit Startwerten (Pro: weniger Nachrichten; Contra: ungeprüft, kann gute Coins
  ausschließen).
- Default: Halter-Anstiegsregel sofort aktiv (sie folgt direkt aus Abschnitt 2.1 der Prüfung); Profil erst nach
  bestandener Zeitsplit-Prüfung laden; Schwellen bis dahin unverändert, Änderungen nur mit Datum und Begründung
  hier eintragen; Mint-Liste nur mit `--dry-run`-Schätzung und `--max-mints` ≤ 20.
- Blockiert: keinen Freeze.
- Status: `offen`.
