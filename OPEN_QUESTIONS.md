# OPEN_QUESTIONS – Edge Lab

Regel: Unklarheiten werden hier notiert statt geraten. Jede Frage hat eine ID, einen Default (falls
unentschieden) und die Angabe, welchen Freeze sie blockiert. Prereg-Dokumente verweisen nur auf IDs.

Legende Kennzeichnung von Fakten in allen Edge-Lab-Dokumenten:

- **[direkt geprüft]** – Seite/Datei wurde am Abrufdatum tatsächlich geladen (z. B. PyPI-JSON, GitHub-Raw).
- **[Snippet]** – nur als WebSearch-Snippet der genannten offiziellen URL gesehen; die Seite selbst war
  wegen der Netzwerk-Policy der Arbeitsumgebung nicht abrufbar (siehe OQ-007).
- **NICHT VERIFIZIERT** – auf keiner abrufbaren Quelle bestätigt.

Status-Werte: `offen`, `entschieden`, `entschieden (Experte)`, `geschlossen`. Seit 2026-10-03 entscheidet
der Experte (`docs/experte.md`) offene Punkte außerhalb seiner Eskalationsliste selbst; jede Entscheidung
steht hier mit Datum und im Outcome-Register des Experten mit Prüftermin.

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
- Status: `entschieden (Experte)` am 2026-10-03, E-003 in `docs/experte.md`: Default gilt. Revision, wenn die
  Statuszeile mehr als 1 000 Einheiten je Stunde zeigt oder weniger als 5 GO am Tag kommen.

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
- Status: `entschieden (Experte)` am 2026-10-03, E-004: Prereg-Entwurf EXP003 wird geschrieben, sobald 200 Alarme
  aus mindestens 30 Stunden vorliegen; bis dahin keine Regeländerung aus Papier-Reports (kein Tuning auf dem
  Prüfdatensatz). Der Freeze selbst bleibt beim Nutzer.

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
- Status: `entschieden (Experte)` am 2026-10-03, E-002: Default gilt (Halter-Anstieg aktiv, Profil erst nach
  bestandener Zeitsplit-Prüfung, Schwellen unverändert bis 200 Alarme). Fragen (a)–(e) bleiben als Prüfpunkte
  für den ersten `tape report` mit mindestens 100 GO.

## OQ-028 – Sniper: Narrativ-Welle aus dem Launch-Strom (Thema, Rang, Quelle) – record-only

- Datum: 2026-10-03
- Kontext: `docs/sniper_review.md` Abschnitt 4.2, Modul `narrative.py` (`ThemeRegistry`), Nutzerwunsch „früher
  Infos über ein starkes Narrativ".
- Befund: Die früheste Narrativ-Information im eigenen Datenstrom ist die Launch-Welle eines Themas (mehrere
  Launches mit demselben Begriff von verschiedenen Devs in wenigen Minuten). Sie wurde bisher nur negativ genutzt
  (KOPIE). Ab 0.3.3 zählt das Themen-Register je Begriff Launches und Devs im 10-Minuten-Fenster gegen die
  Grundrate der letzten 6 Stunden, bestimmt den Rang eines Coins in seiner Welle nach Außen-Zufluss und erkennt
  gemeinsame Quellen in den Metadaten (gleicher Tweet, gleicher Telegram-Link). Alles ohne zusätzliche RPC-Last.
- Parameter ohne Daten gesetzt: Fenster 10 min, Historie 6 h, Welle ab 4 Launches von 3 Devs und mindestens dem
  Vierfachen der Grundrate (Mindestgrundrate 0,5 je Fenster), Quelle ab 2 Launches von 2 Devs in 30 min,
  Begriffe ab 3 Zeichen ohne Füllwörter, Beschreibung auf 200 Zeichen gekürzt.
- Fragen: (a) Trennt Wellen-Rang 1 Rendite gegen Kontrollen (Test wie Umbau-Plan Punkt 14)? (b) Welche Schwellen
  (Launches, Devs, Verhältnis) markieren Wellen, die Geld anziehen, statt Bot-Serien eines Deployers?
  (c) Zweiter IPFS-Gateway als Rückfall: welcher ist frei, stabil und dokumentiert? Kandidaten sind NICHT
  VERIFIZIERT (Netzwerk-Policy, OQ-007). (d) Soll die Zeile `Them` auch bei WIDERRUF/RUG erscheinen?
- Entscheidung (Experte, E-001 in `docs/experte.md`): record-only bauen, Zeile `Them …` in BLICK/GO, Feld
  `narrativ` in Record und Papier-Kontext, kein Gate. Revisionsauslöser: Nach 200 Alarmen keine Differenz
  zwischen Rang 1 und Kontrollen → bleibt Information; Differenz vorhanden → Gate mit Zeitsplit-Prüfung wie beim
  Profil (OQ-027).
- Blockiert: keinen Freeze.
- Status: `entschieden (Experte)` am 2026-10-03; Fragen (a)–(d) offen als Prüfpunkte.

## OQ-029 – Eigener Coin-Launch zum Profit (mit DEX-Boost): Eskalation an den Nutzer

- Datum: 2026-10-03
- Kontext: Frage des Nutzers „was wenn ich selbst einen guten Coin launche und den auf DEX booste?";
  `docs/experte.md` Eskalationspunkte 1 (Geld), 3 (Live-Kapital) und 7 (Rechtsrisiko); widerspricht der Regel
  Edge-First („kein Live-Kapital, keine Käufe/Abos"), die der Nutzer selbst gesetzt hat.
- Befund (Mechanik, Evidenzstufe 5, Zahlen aus den geprüften Quellen): Einnahmen eines Creators auf der Kurve sind
  die Creator-Fee von 0,30 % des Volumens [direkt geprüft, fees.png, Stand 2025-08-29; seit 2025-09-01 dynamisch];
  bei Holder-Rewards-Coins ist der Creator eine PDA, die Fee fließt an die Halter [direkt geprüft, pump-public-docs,
  2026-09-29]. Graduation-Basisrate 0,2 % bis 2,7 % [Snippet, OQ-019]. Preise und Wirkung von DexScreener-Boosts:
  NICHT VERIFIZIERT (Host in der Arbeitsumgebung gesperrt). Steuer und Recht (EU-MiCA, deutsche Besteuerung
  privater Veräußerungen, Betrugstatbestände bei irreführender Werbung): NICHT VERIFIZIERT, nur mit Berater.
- Frage: Soll Kapital in einen eigenen Launch (Create-Transaktion, Dev-Kauf, Boosts) fließen?
- Optionen: (a) nichts tun, Edge-First weiterführen; (b) transparenter Launch ohne bezahlte Werbung, Einnahmen
  nur aus der Creator-Fee, Dev-Bestand offengelegt und nicht in die Nachfrage verkauft, kleiner fester Betrag mit
  vorab festgelegtem Erfolgskriterium (Creator-Fee ≥ Kosten) und Steuer-/Rechtsprüfung davor; (c) Launch mit
  bezahlter Werbung und Verkauf des eigenen Bestands in die angelockte Nachfrage – das ist das Muster, das der
  Sniper als DEV-DUMP/RUG markiert; es schadet den Käufern, ist rechtlich riskant und wird hier nicht unterstützt.
- Empfehlung des Experten: (a) jetzt; (b) frühestens nach der Messung E-008 (Creator-Fee-Verteilung aus dem
  eigenen Tape) und nach der Beratung; (c) nein.
- Default, wenn keine Antwort: (a).
- Blockiert: keinen Freeze.
- Status: `offen` (Eskalation, Entscheidung beim Nutzer).

## OQ-030 – DexScreener-Bezahlsignale (Boosts, „Dex paid") als Call-Quelle: EXP004-Kandidat, record-only

- Datum: 2026-10-03
- Kontext: Nutzerfrage „wie funktioniert dieses paid dex, damit wir daraus profitieren können";
  `docs/dexscreener_paid.md`; Modul `tools/holder-scorer/holder_scorer/dexpaid.py` (`dex beobachten`, `dex report`).
- Befund: Boosts heben 12–24 h den Trending-Score [Snippet, offizielle Doku], Preise 99–3 999 USD je Paket
  [Snippet, Drittanbieter, NICHT VERIFIZIERT]; Enhanced Token Info („Dex paid") ab 299 USD [Snippet, Marktplatz].
  Beides ist öffentlich und ohne Schlüssel abfragbar (60/300 Anfragen je Minute, Referenz-Spiegel [direkt geprüft]).
  Einzige bekannte Wirkungsmessung (dethective, 2024): geboostete Token im Mittel −48 %, Methodik unbekannt.
- Fragen: (a) Verdient ein Follower nach Boost/Profil netto (Horizonte 5/15/60 min) oder liefert er die
  Exit-Liquidität? (b) Welche Kontrollgruppe (nicht bezahlte Token gleicher Größe und Alters) ist aus der freien
  API bildbar? (c) Erlauben die API-Nutzungsbedingungen den Dauerbetrieb (Seite gesperrt, nicht gelesen)?
  (d) Höchstzahl Adressen je Tokens-Aufruf (30?) – NICHT VERIFIZIERT. (e) Wie oft bekommen unsere eigenen
  Alarm-Coins später ein Bezahlsignal, und sagt das Frühprofil es voraus?
- Entscheidung (Experte, E-009): record-only messen; keine Boosts kaufen, kein Creator-Weg (OQ-029); Ergebnis
  erst mit ≥ 200 Ereignissen aus ≥ 30 Stunden und Kontrollgruppe als Hinweis lesen; Gebühr-Annahme 50 bps je Seite.
- Default, wenn keine Antwort: so belassen.
- Blockiert: keinen Freeze.
- Status: `entschieden (Experte)` am 2026-10-03; (b)–(e) offen als Prüfpunkte.
- Nachtrag 2026-10-04: Der Nutzer präzisiert den Wunsch zu einem **fairen** Launch (kleiner Teilverkauf, Coin soll
  weiterlaufen, Halter sollen gute Chancen haben, Einsatz von X/Telegram). Der Experte liefert dafür Wissen statt
  Entscheidung: `docs/fair_launch.md` (Graduation-Mechanik, Fairness-Regeln entlang der Sniper-Warnungen,
  Verkaufsplan ≤ 25 % nach Graduation in Tranchen, Holder-Rewards als Fairness-Signal, Recht/Steuern NICHT
  VERIFIZIERT) und `launch rechner` (E-010): Dev-Kauf 1 SOL ≈ 3,4 % Supply, Position bei Graduation ≈ 14,1 SOL,
  Verkauf eines Viertels ≈ 3,4 SOL netto bei ≈ 6 % Kursimpact, Creator-Fee bis Graduation ≈ 0,5 SOL (Annahme
  Volumen 2 × Zufluss). Die Entscheidung über Kapital, Enhanced Token Info (299 USD) und den Rechtsrahmen bleibt
  beim Nutzer (Eskalation 1, 3, 7); Default unverändert: kein Launch ohne Berater und ohne Budget-Obergrenze.

## OQ-031 – Sniper: Fairness-Gate als Pflicht für BLICK/GO (Verschärfung auf Anweisung des Nutzers)

- Datum: 2026-10-04
- Kontext: Nutzeranweisung „den Sniper jetzt genau nach den Prinzipien verbessern und verschärfen"; Prinzipien aus
  `docs/fair_launch.md` Abschnitt 3; Modul `tools/holder-scorer/holder_scorer/fair.py` (0.3.4).
- Umsetzung: Schnelle Prüfungen gelten für BLICK und GO (Dev-Anteil aus Kauf und Bestand, kein Dev-Verkauf, Bundle-Anteil
  und Zahl fremder Wallets im Create-Fenster, keine Kopie eines Launches der letzten Stunde, kein unsichtbarer Float,
  keine Bots/Wash); langsame Prüfungen nur für GO (Creator-Historie: nicht frisch, keine Serie toter Launches;
  Metadaten: Social-Links und Bild). Unbekannt zählt nicht als sauber: GO wartet auf Historie und Metadaten, solange
  RPC bzw. Nebenabfragen vorhanden sind; fehlende Metadaten sind ein Fehlen. Sagt der Score GO und ein Prinzip ist
  endgültig verletzt, geht einmal ⛔ GESPERRT heraus (Aufzeichnung, im Standard keine Handy-Nachricht), nach BLICK
  zusätzlich ↩️ WIDERRUF mit dem verletzten Prinzip. Zeile `Fair` in jeder Nachricht, Feld `fair` in Record und
  Papier-Kontext.
- Schwellen ohne Daten gesetzt: Stufe 1 Dev ≤ 5 %, ≤ 3 Create-Wallets; Stufe 2 Dev ≤ 7 %, ≤ 5 Wallets; Stufe 3 Dev ≤ 10 %,
  Dev-Verkauf ≤ 10 %, ≤ 8 Wallets, keine Kopie-/Historie-/Metadaten-Pflicht. Alle: Wash ≤ 20 % (Stufe 3: 30 %),
  Bots ≤ 25 % (30 %), unsichtbarer Float < 2 %, Historie ab 3 Vor-Launches mit ≥ 50 % tot gesperrt, Socials ≥ 2 + Bild
  (Stufe 3: ≥ 1, kein Bild nötig). `--no-fair`, `--fair-dev-max`, `--fair-socials`, `--fair-ohne-historie`.
- Spannung zu R2 („erst messen, dann filtern"): Die Verschärfung ist Nutzeranweisung und gilt sofort. Messbar bleibt sie,
  weil jeder gesperrte GO als GESPERRT-Record mit Grund vorliegt: `tape report --tiers GO` gegen `--tiers GESPERRT`
  zeigt, ob die gesperrten Coins schlechter liefen als die durchgelassenen.
- Fragen: (a) Welche Schwelle trennt Rendite (Dev-Anteil 5 % vs. 7 % vs. 10 %)? (b) Kostet die Historien-Pflicht zu viele
  GO, wenn das RPC-Budget knapp ist (Stufe 1 mit Budget 1000)? (c) Sollen WIDERRUF-Gründe aus dem Gate auch nach GO einen
  RUG auslösen (Dev verkauft nach GO)? (d) Kopie-Sperre vs. Wellen-Rang 1 (OQ-028): ein Kopierer mit dem meisten Zufluss
  wäre heute gesperrt.
- Default: so belassen bis zum ersten `tape report` mit ≥ 100 GO und ≥ 100 GESPERRT; dann Schwellen nur mit Zeitsplit anpassen.
- Blockiert: keinen Freeze.
- Status: `entschieden (Nutzer)` am 2026-10-04; Prüfpunkte (a)–(d) offen.

## OQ-032 – Sniper 0.3.5 „Abstimmung": alle Teile auf dieselben Prinzipien ausgerichtet

- Datum: 2026-10-04
- Kontext: Nutzerauftrag „alles genau so abstimmen, wie es sein sollte"; Plan und Gegenprüfung (Plan-Agent) am
  2026-10-04; `docs/sniper_review.md` Abschnitt 4, `docs/experte.md` E-012.
- Entschieden (Kohärenz, keine Kalibrierung): (1) Dev-Faktor des Scores monoton: bis `dev_small_buy` (3 %) volle
  Punkte, zur Mitte 40 %, ab `dev_big_hold` (10 %) null; vorher 90 % der Punkte für 6,7–27 %, die das Gate sperrt.
  (2) WIDERRUF auch nach GO, wenn ein schnelles Fairness-Prinzip neu verletzt wird (Dev verkauft unter der
  DEV-RAUS-Schwelle, Bundle sichtbar); einmal je Token, RUG unverändert. (3) Kopie-Prüfung gerichtet nach
  Registrierungsreihenfolge: das Original einer Welle wird nicht rückwirkend zur Kopie (vorher falscher WIDERRUF nach
  GO möglich). (4) Zähler `go_wartet` (GO nur durch ladende Historie/Metadaten zurückgehalten) und Statuszeile mit
  WIDERRUF/GESPERRT/wartenden GO. (5) Papier-Strategien respektieren die schnellen Fairness-Prüfungen
  (`--paper-ohne-fair` zum Vergleich). (6) `tape report` Gate-Prüfung GO gegen GESPERRT (Block-Bootstrap der
  Differenz, Lesart „Sperre richtig/unnötig/offen"). (7) Startbefehle mit `gesperrt` in `--tiers`.
- Prüfpunkte: (a) Knickpunkte 3/6,5/10 % sind Richtung ohne Daten; (b) Papier-Statistik ab 0.3.5 nicht mit älteren
  Aufzeichnungen vergleichbar (Regel-Hash trennt); (c) ein Token mit WIDERRUF nach BLICK und späterem GO bekommt
  keinen zweiten WIDERRUF (einmal je Token); (d) Gate-Prüfung braucht ≥ 2 Alarmstunden je Gruppe für ein Intervall.
- Blockiert: keinen Freeze.
- Status: `entschieden (Experte)` am 2026-10-04 auf Nutzerauftrag; Prüfpunkte offen.

## OQ-033 – Sniper 0.3.6 „Außenquellen": Informationen nicht nur aus dem eigenen Papier-Test

- Datum: 2026-10-04
- Kontext: Nutzerauftrag „Informationen nicht nur aus unserem Paper-Trade-Test holen, sondern auch woanders"; Plan und
  Gegenprüfung (Plan-Agent) am 2026-10-04; `docs/quellen_extern.md`, `docs/experte.md` E-013. Alle Anbieter-Hosts in der
  Arbeitsumgebung gesperrt, Belege [Snippet] oder NICHT VERIFIZIERT; der Code hebt Rohdaten auf.
- Entschieden (Experte, record-only, R2/R4/R5): (1) PumpPortal `subscribeMigration` auf der bestehenden WebSocket-Verbindung
  (kostenlos, null RPC): Zeile `graduierung` je Migration mit `alarm` aus dem Alarm-Gedächtnis (höchster Tier je Mint,
  5 000 Einträge) und `roh`; Dispatch nach `txType`, nicht nach dem Rückgabewert von `on_launch`. (2) `quellen nachlauf`:
  DexScreener `/latest/dex/tokens` (30 Mints je Anfrage, 250 je Minute) für Alarm- und Kontroll-Coins nach 1 h und 24 h,
  eine Zeile je Coin und Horizont, Alarme vor Kontrollen, idempotent, kein RPC. (3) Rugcheck-Kurzbericht je GO/GESPERRT nur
  mit `--rugcheck`, direkt über `run_side_task` in der HTTP-Gruppe (nicht `_spawn`, das finale oder entfernte Token
  ausließe), einmal je Token, Zeile in jedem Fall. (4) `tape report --extern`: Graduation extern je Tier und Kontrollen
  (Nenner nur Alarme im Reifefenster `erster_t ≤ alert_at ≤ letzter_t − 24 h`, Rest „offen"; zweiter Marker: Nachlauf-Paar
  außerhalb `pumpfun`), Überleben (Paar mit Liquidität ≥ 1 000 USD), Rugcheck-Trennung am Median (Lesart ab 20 je Hälfte),
  Grundrate 0,26–1,4 % als Plausibilitätsband für die Kontrollen. (5) `profil bauen --extern`: Graduierungen neueste zuerst
  als gute Referenz, zusammen mit `--mints` durch `--max-mints` begrenzt; Coins im Tape bekommen das Außen-Label ohne RPC
  (Graduation ist die spätere Wahrheit, wie `label_from_rows`). (6) `fetch_ticks` paginiert über die Bonding-Curve-Adresse
  statt über den Mint (nach der Graduation sammelt der Mint alle PumpSwap-Trades, die Kurve nicht). (7) `rules_hash` ohne
  Dateinamen und record-only-Schalter (`tape_path`, `tape_sample`, `extern_path`, `rugcheck`).
- Prüfpunkte: (a) Feldnamen des Migrationsereignisses (`mint`, `txType`, `pool`, `signature`) NICHT VERIFIZIERT – erste
  `roh`-Zeilen auf dem Rechner des Nutzers lesen und hier nachtragen; (b) Rugcheck: Antwortform und Rate-Limit NICHT
  VERIFIZIERT (`roh` bei unerwarteter Form), Abdeckung frischer Coins unbekannt; (c) Überlebens-Schwelle 1 000 USD ist
  Annahme; (d) Feed-Reife 24 h ist Annahme (Graduationen nach Tag 1 zählen nicht); (e) ob DexScreener Coins auf der Kurve
  (`dexId pumpfun`) listet, ist ungeprüft – viele `fehlt`-Zeilen bei Kurven-Coins wären kein Sterben, sondern fehlende
  Abdeckung; dann GeckoTerminal-OHLCV (30 Aufrufe je Minute [Snippet]) als Nachlauf-Alternative; (f) Kurven-Adresse als
  Signaturquelle: `bonding_curve` steht in den Konten von create, create_v2, buy, sell und migrate [direkt geprüft: IDL pump.json via
  raw.githubusercontent.com/pump-fun/pump-public-docs, 2026-10-04]; die Kurvenhistorie ist damit vollständig und endet mit der Migration; (g) externe Narrativ-
  Quellen (Telegram, X) bleiben Eskalation (E-005), Birdeye bleibt Pilot (E-006).
- Default: so belassen bis zum ersten `tape report --extern` mit ≥ 100 GO und 24 h Feed-Reife; kein Gate aus Außenquellen vor
  einer Zeitsplit-Prüfung.
- Blockiert: keinen Freeze.
- Status: `entschieden (Experte)` am 2026-10-04 auf Nutzerauftrag; Prüfpunkte (a)–(g) offen.
