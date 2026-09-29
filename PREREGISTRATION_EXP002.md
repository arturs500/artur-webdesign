# PREREGISTRATION_EXP002 – Pump.fun Dev-Follow (Paper-only)

| Feld | Wert |
|---|---|
| Experiment | EXP002 |
| Status | **DRAFT v0.1** – nicht eingefroren, kein Hash |
| Datum | 2026-09-29 |
| Projekt | Edge Lab – Regel Edge-First: kein Bot-Bau, kein Live-Kapital, keine Käufe/Abos, keine API-Keys im Repo |
| Vorgänger | EXP001 (Telegram-Calls; Prereg v0.3, Freeze offen – FREEZE_CHECKLIST.md) |
| Offene Punkte | nur als IDs, siehe OPEN_QUESTIONS.md (OQ-009 … OQ-023) |

Kennzeichnung von Fakten: **[direkt geprüft]** (Quelle am Abrufdatum geladen), **[Snippet]** (nur
Suchergebnis-Snippet, Seite gesperrt), **NICHT VERIFIZIERT**. Werte, die beim Freeze festgelegt werden
müssen, sind mit **BEIM FREEZE FIXIEREN** markiert; bis dahin gelten die genannten Defaults.

---

## 1. Hypothese (wörtlich, unveränderlich nach Freeze)

> "Launches von Pump.fun-Devs mit hoher historischer Graduation-Rate (point-in-time berechnet, min. 10
> frühere Launches) liefern Followern bei Entry T+{5,30,60}s positive Netto-Returns nach Fees und Slippage."

Operationalisierung: Abschnitte 4 (Treatment), 6 (Simulation/Kosten), 7–9 (Metriken, Statistik,
PASS/FAIL). Der **Primärtest** ist eine einzige, vorab festgelegte Kombination (Entry T+30 s, Exit
+5 min, Abschnitt 8.5); T+5 s und T+60 s sowie weitere Exit-Horizonte sind sekundär.

## 2. Definitionen

- **Programm:** Pump.fun Bonding-Curve-Programm `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`
  [direkt geprüft] (Quelle: https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/PUMP_PROGRAM_README.md,
  abgerufen 2026-09-29).
- **Launch (Event):** ein `create`/`create_v2`-Aufruf mit CreateEvent (mint, bonding_curve, user, creator,
  timestamp, Startreserven, quote_mint) [direkt geprüft, Decoder aus der offiziellen IDL:
  https://raw.githubusercontent.com/sevenlabs-hq/carbon/main/decoders/pumpfun-decoder/src/types/create_event.rs].
- **Dev:** der `creator`-Pubkey des CreateEvents (kann vom Signer abweichen [direkt geprüft, PUMP_PROGRAM_README]).
  Dev-Identität = Wallet; Wallet-Clustering findet in EXP002 nicht statt (OQ-018).
- **Entscheidungszeitpunkt `t_dec`:** Position (slot, tx_index) der Create-Transaktion; `t_create` =
  Blockzeit des Create-Slots (Unix-Sekunden, geschätzt aus Vote-Timestamps [direkt geprüft:
  https://raw.githubusercontent.com/solana-foundation/solana-com/main/apps/docs/content/docs/en/rpc/http/getblocktime.mdx]).
- **Trade:** TradeEvent (mint, sol_amount, token_amount, is_buy, user, timestamp, virtual_sol_reserves,
  virtual_token_reserves, real_sol_reserves, real_token_reserves, fee_basis_points, fee,
  creator_fee_basis_points, creator_fee, …) [direkt geprüft:
  https://raw.githubusercontent.com/sevenlabs-hq/carbon/main/decoders/pumpfun-decoder/src/types/trade_event.rs].
- **Graduation (Complete):** `complete = true` wird am Ende eines `buy` gesetzt, wenn `real_token_reserves == 0`
  [direkt geprüft, PUMP_PROGRAM_README]. `t_complete` = Blockzeit dieses Trades (CompleteEvent), **nicht**
  die spätere Migrations-Transaktion (CompletePumpAmmMigrationEvent).
- **Graduiert innerhalb 7 Tagen:** `t_complete ≤ t_create + 7 d`. Diese Definition gilt identisch für
  Dev-Historie (Abschnitt 4) und Basisrate (Abschnitt 12).
- **Kurvenzustand:** (vS, vT, rS, rT) = virtuelle SOL-/Token-Reserven und reale Reserven nach dem letzten
  Trade bis zu einem Zeitpunkt; Anfangszustand aus dem CreateEvent (nicht aus Konstanten, wegen Mayhem-Mode
  und Programmänderungen 2026, OQ-023).
- **Standard-Initialzustand (Plausibilitätswert):** Global-Parameter [direkt geprüft, PUMP_PROGRAM_README]:
  `initial_virtual_token_reserves` = 1 073 000 000 000 000 (6 Dezimalstellen → 1,073 Mrd. Token),
  `initial_virtual_sol_reserves` = 30 000 000 000 Lamports (30 SOL), `initial_real_token_reserves` =
  793 100 000 000 000, `token_total_supply` = 1 000 000 000 000 000. Abgeleitet: Startpreis
  30 / 1,073e9 ≈ 2,796e-8 SOL je Token, Start-Mcap ≈ 27,96 SOL; Graduation nach ca. 85 SOL Nettozufluss
  (Mcap ≈ 411 SOL).

## 3. Population und Analysefenster

- **Population:** alle Launches des Programms im Analysefenster [D0, D1) mit SOL als Quote-Mint
  (USDC-quotierte Coins ausgeschlossen, OQ-023). **Keine Wallet-Vorauswahl**: alle Devs, alle Launches.
- **Analysefenster:** 30 zusammenhängende Tage, UTC. **BEIM FREEZE FIXIEREN** (OQ-009). Die Fensterlänge darf
  vor dem Freeze durch eine reine Zählung der Treatment-Events dimensioniert werden (Abschnitt 11).
- **Lookback:** rollierend je Event, L = 90 Tage vor `t_create` (**BEIM FREEZE FIXIEREN**, OQ-009).
  Datenbedarf: Creates und Completes ab D0 − L − 7 d; Trades nur für Treatment-Events und Kontrollen.
- **Mayhem-Mode-Coins** (variable virtuelle Reserven) bleiben in der Population, werden geflaggt und in
  einer Sensitivität ausgeschlossen (OQ-023).

## 4. Dev-Historie (point-in-time) und Treatment-Definition

Kein Look-ahead: Für ein Event mit Position `t_dec` dürfen ausschließlich Daten mit Position
strikt vor `t_dec` verwendet werden. Konkret:

1. **Gereifte Vor-Launches des Devs:** alle Launches desselben `creator` mit
   `t_create_prev ∈ [t_create − L, t_create − 7 d]`. Launches der letzten 7 Tage vor dem Event zählen
   nicht (Rechtszensierung: ihre Graduation wäre noch offen).
2. `n_prev` = Anzahl gereifter Vor-Launches; `grad_prev` = Anzahl davon mit `t_complete_prev ≤ t_create_prev + 7 d`
   (damit automatisch `t_complete_prev < t_create`).
3. **Treatment-Regel (eine Regel, Default, BEIM FREEZE FIXIEREN, OQ-010):**
   `n_prev ≥ 10` **und** `grad_prev ≥ 2` **und** `grad_prev / n_prev ≥ 0,10`.
   Hinweis: Bei `n_prev < 20` wirkt `grad_prev ≥ 2` als 20-%-Schwelle; das ist gewollt (Schutz gegen einen
   einzelnen Zufallstreffer).
4. **Sekundär (deskriptiv, ändert PASS/FAIL nicht):** Relativ-Regel – Wilson-95%-Untergrenze von
   `grad_prev / n_prev` größer als die Basisrate des Vorzeitraums (Abschnitt 12).
5. **Kontrollpool:** alle Launches der Population, die zu ihrem eigenen `t_dec` **nicht** Treatment sind
   (inklusive Devs mit `n_prev < 10`), mit `creator ≠ creator` des Treatment-Events.
6. Die Graduation des Kandidaten-Launches selbst fließt weder in Treatment-Zuweisung noch in Matching ein
   (nur in die Exit-Behandlung, Abschnitt 6.5).

## 5. Baseline (gematchte Zufalls-Launches) und Self-Buy-Flag

### 5.1 Initialzustand und Self-Buy

- **Initialzustand** eines Launches = Kurvenzustand am **Ende des Create-Slots** (alle Transaktionen des
  Slots einbezogen); `initial_mcap_sol = (vS / vT) × token_total_supply` in SOL.
- **Self-Buy:** `self_buy_sol` = Summe `sol_amount` aller Buys mit `user = creator` im Create-Slot
  (typisch: "create with initial buy" in derselben Transaktion [direkt geprüft:
  https://raw.githubusercontent.com/pump-fun/pump-fun-skills/main/create-coin/SKILL.md]).
  `self_buy_flag = (self_buy_sol > 0)`. Der Standard-Initial-Mcap (27,96 SOL, Abschnitt 2) dient nur als
  Plausibilitätscheck: `initial_mcap_sol > Standard` muss mit `self_buy_flag` übereinstimmen; Abweichungen
  werden gezählt. Käufe fremder Wallets im Create-Slot (Bundles) sind nicht vom Self-Buy unterscheidbar
  (Limitation, OQ-018); ihre Summe wird als `other_buys_create_slot_sol` deskriptiv mitgeführt.
- Das Flag ist ein **Stratifizierer**: Der Primärtest läuft über alle Treatment-Events; die getrennte
  Auswertung nach `self_buy_flag` (0/1) ist sekundär.

### 5.2 Matching

- **Strata:** 6-Stunden-Block (UTC, 00/06/12/18) × Mcap-Bin. Bin 0 = kein Self-Buy (Standard-Initialzustand);
  Bins 1–5 = Quintile von `self_buy_sol` innerhalb aller Launches mit Self-Buy im Analysefenster
  (Quantilgrenzen einmal berechnet und in der Auswertung dokumentiert). Dezile über den Initial-Mcap sind
  wegen des Massepunkts beim Standardwert nicht definiert.
- **Kontrollen:** je Treatment-Event k = 5 Launches aus dem Kontrollpool desselben Stratums, ohne
  Zurücklegen über alle Treatment-Events, Zufallsauswahl mit festem Seed (**BEIM FREEZE FIXIEREN**, OQ-016).
- **Fallback-Hierarchie (fix):** (1) selbes Stratum; (2) weniger als 5 verfügbar → alle nehmen, `k_i`
  protokollieren; (3) `k_i < 2` → Nachbar-Mcap-Bin im selben Block, dann angrenzender 6-h-Block im selben
  Bin; (4) weiterhin `k_i < 2` → Event aus der gepaarten Analyse ausschließen, im ungepaarten Primärtest
  behalten. Anteil ausgeschlossener Events berichten; über 10 % → Warnhinweis im Bericht.
- Kontrollen werden **identisch** simuliert (gleiche Entry-/Exit-Zeitpunkte relativ zu ihrem `t_create`,
  gleiche Ordergröße, gleiche Kosten, gleiche Ausschlussregeln).

## 6. Simulation und Kostenmodell (Paper-only)

### 6.1 Entry und Exit

- Entry-Zeitpunkte: `t_create + δ`, δ ∈ (5 s, 30 s, 60 s). Der Fill erfolgt auf dem Kurvenzustand **nach
  allen** realen Trades mit `block_time ≤ t_create + δ` (unsere Transaktion landet als letzte in dieser
  Sekunde – deterministische Worst-Case-Ordnung). T+5 s ist mit realer Detektions- und Landing-Latenz eine
  **optimistische Grenze** und wird so gekennzeichnet.
- Ordergröße S = 0,5 SOL (Default; Sensitivität 0,1 und 1,0 SOL; **BEIM FREEZE FIXIEREN**, OQ-011).
- Exit-Zeitpunkte: `t_entry + H`, H ∈ (5 min, 15 min, 60 min); primär H = 5 min. Exit = vollständiger
  Verkauf der Position auf dem Kurvenzustand nach allen realen Trades mit `block_time ≤ t_entry + H`.
- Keine Trades zwischen Entry und Exit → Exit auf dem durch den eigenen Buy veränderten Zustand (nur
  eigener Impact und Gebühren). Das ist der Normalfall für tote Launches.

### 6.2 Bonding-Curve-Mathematik (kein pauschaler Slippage-Satz)

Konstantprodukt auf den virtuellen Reserven ("based on Uniswap V2 and uses synthetic x and y reserves"
[direkt geprüft, PUMP_PROGRAM_README]). Mit `k = vS × vT` in Basiseinheiten (Lamports, Token-Basiseinheiten),
Integer-Arithmetik wie das Programm (u64, Abrundung):

- **Buy** mit Netto-SOL `x`: `tokens_out = vT − floor(k / (vS + x))`; danach `vS' = vS + x`, `vT' = vT − tokens_out`,
  `rT' = rT − tokens_out`; `tokens_out` ist zusätzlich auf `rT` begrenzt (Graduation, Abschnitt 6.5).
- **Sell** von `y` Token: `sol_out_gross = vS − floor(k / (vT + y))`; danach `vT' = vT + y`, `vS' = vS − sol_out_gross`.
- Preis `p = vS / vT`; Mcap `= p × token_total_supply`.
- **Ob die Gebühr beim Buy vor oder nach der Kurvenrechnung abgezogen wird, ist NICHT VERIFIZIERT.** Die
  Reihenfolge wird in der Simulator-Validierung (Abschnitt 6.6) aus realen Trades bestimmt und dann fixiert.

### 6.3 Gebühren

- **Pump.fun-Gebühr:** primär die **protokollierten Fee-Felder je Trade** (`fee_basis_points`, `fee`,
  `creator_fee_basis_points`, `creator_fee`, ggf. `cashback_fee_basis_points`, `buyback_fee_basis_points`)
  aus dem TradeEvent [direkt geprüft, trade_event.rs]. Für die eigene simulierte Order gilt der Fee-Satz des
  zeitlich letzten realen Trades vor dem Fill (gleicher Mcap-Bereich), sonst die Tabelle:
  Bonding Curve **0,30 % Creator + 0,95 % Protokoll = 1,25 %** je Seite [direkt geprüft, offizielle
  Gebührentabelle fees.png: https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/fees.png];
  dynamische Gebühren gelten seit "Monday, September 1, 20:00 UTC" [direkt geprüft:
  https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/FEE_PROGRAM_README.md] (Jahr aus dem
  Wochentag abgeleitet: 2025); davor Legacy `fee_basis_points == 100` [direkt geprüft, PUMP_PROGRAM_README].
  Der Fee-Satz ist damit **zeitindexiert**, nicht konstant (OQ-012).
- **Gebühr auf beiden Seiten:** Buy `x = S × (1 − f_buy)` fließt in die Kurve; Sell `sol_net_out = sol_out_gross × (1 − f_sell)`.

### 6.4 Transaktionskosten

- Basisgebühr **5 000 Lamports je Signatur**, fällig auch bei Fehlschlag [direkt geprüft:
  https://raw.githubusercontent.com/solana-foundation/solana-com/main/apps/docs/content/docs/en/core/fees/fee-structure.mdx].
  Annahme: 1 Signatur je Transaktion; Buy + Sell (+ Close) = 2–3 Transaktionen.
- Priority-Fee `= ceil(cu_price_µLamports × cu_limit / 1 000 000)`, berechnet auf das **angeforderte**
  CU-Limit [direkt geprüft, fee-structure.mdx und compute-budget.mdx]. CU-Limit 100 000 je Buy/Sell
  (Empfehlung der pump.fun-FAQ [direkt geprüft:
  https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/FAQ.md]).
  Szenarien für `cu_price`: low 10 000, **medium 120 000 (primär)**, high 500 000 µLamports/CU
  (Beispielwerte aus der Helius-Priority-Fee-Doku [direkt geprüft:
  https://raw.githubusercontent.com/helius-labs/core-ai/main/helius-plugin/skills/build/references/priority-fees.md];
  keine Marktstatistik). Alternative, falls die Daten es erlauben: Median der CU-Preise der realen
  Pump.fun-Trades im Entry-Slot (OQ-013). Beispiel medium: 5 000 + 12 000 = 17 000 Lamports je Transaktion.
- Jito-Tip: optional 0,0001 SOL je Transaktion (Default im offiziellen pump.fun-Skill [direkt geprüft:
  https://raw.githubusercontent.com/pump-fun/pump-fun-skills/main/swap/SKILL.md]); primär **ohne** Tip,
  Sensitivität mit Tip.
- Associated-Token-Account: Rent-Exempt-Einlage für den Token-Account beim Kauf (Größenordnung 0,002 SOL,
  **NICHT VERIFIZIERT** – am Stichtag per `getMinimumBalanceForRentExemption(165)` abfragen, OQ-013);
  Rückholung durch `closeAccount` nach vollständigem Verkauf als dritte Transaktion (Basisgebühr).
  Primär: Rent als Kosten, Rückholung minus Basisgebühr als Ertrag; Sensitivität ohne Rückholung.

### 6.5 Eigener Preiseinfluss, Graduation vor Exit, Ausschlüsse

- **Eigener Impact:** (a) **Replay (primär):** der eigene Buy verändert den Zustand; alle realen Folge-Trades
  werden mit **gleichen Inputs** (Buys in SOL, Sells in Token) auf den veränderten Zustand neu angewendet,
  dann der eigene Sell. (b) **Overlay (Sensitivität):** realer Zustand zum Exit-Zeitpunkt plus eigenes
  Delta. Reaktionen anderer Marktteilnehmer auf unsere Order sind nicht modellierbar (Limitation).
- **Graduation vor Exit** (Complete zwischen Entry und `t_entry + H`), Doppelbehandlung (OQ-015):
  (a) optimistisch: Verkauf zum Kurvenzustand unmittelbar **vor** dem Trade, der `complete = true` setzt,
  abzüglich Gebühren; (b) konservativ: Position bis zum Exit nicht handelbar, Bewertung 0 (Totalverlust der
  eingesetzten Summe). PASS erfordert Bestehen unter **beiden** Varianten. Anteil solcher Events berichten.
- **Nicht handelbar / Ausschluss (symmetrisch für Treatment und Kontrollen):** Kurve bei `t_entry` bereits
  complete; kein Kurvenzustand rekonstruierbar (fehlende Trades); Quote-Mint ≠ SOL. Anzahl und Gründe
  berichten; Schwelle für den Datenqualitäts-Stopp in Abschnitt 9.
- **Slippage-Limit:** primär keines (Fill immer); sekundär Limit 10 % gegenüber dem Preis bei `t_create + δ`
  → "kein Fill" = nur Basis- und Priority-Fee als Kosten (OQ-014).

### 6.6 Simulator-Validierung (Pflichtschritt vor der Auswertung)

Für alle realen Trades eines disjunkten Pilotzeitraums (Abschnitt 11) werden `token_amount` (Buys) bzw.
`sol_amount` (Sells) aus dem Kurvenzustand vor dem Trade mit den Formeln aus 6.2/6.3 rekonstruiert und
mit den protokollierten Werten verglichen. Ziel: Abweichung 0 in Basiseinheiten (Rundungsabweichungen ≤ 1
Einheit dokumentieren). Schlägt die Validierung fehl, ist das Fee-/Formelmodell falsch → Stopp, Korrektur,
Dokumentation im Änderungslog; keine Auswertung des Analysefensters vorher.

### 6.7 Netto-Return je Event

`r = (sol_net_out + rent_back − (S + fees_tx + rent)) / (S + fees_tx + rent)`, alles in SOL, mit
`fees_tx` = Summe aller Basis- und Priority-Fees (und ggf. Tips) der 2–3 Transaktionen; Pump.fun-Gebühren
stecken in `x` und `sol_net_out`. Treffer := `r > 0`.

## 7. Metriken

Primär (Treatment-Events, Primärkombination): mittlerer Netto-Return `mean(r)`; gepaarte Differenz
`d_i = r_i − mean(r_control,i,1..k_i)` und `mean(d)`.
Sekundär/deskriptiv: Median `r`, Trefferquote `P(r > 0)`, Verteilung (Perzentile), winsorisierter
Mittelwert (99. Perzentil), Fragilitätsindikator "Anteil des Gesamt-P&L aus den Top-5 % der Events", Anteil
Graduation-vor-Exit, alles je Entry-/Exit-Kombination, je `self_buy_flag`, je Mayhem-Flag.

## 8. Statistik

1. **Cluster:** Dev (`creator`). Events desselben Devs sind korreliert.
2. **Cap:** maximal N = 20 Events je Dev in der Primäranalyse; bei mehr Events Zufallsauswahl mit festem
   Seed (**BEIM FREEZE FIXIEREN**, OQ-017). Robustheit: ungedeckelt und dev-gleichgewichtet (Gewicht 1/n_dev).
3. **Cluster-Bootstrap:** Devs mit Zurücklegen ziehen, alle (≤ 20) Events des gezogenen Devs übernehmen;
   B = 10 000 Resamples; Perzentil-Intervalle (2,5 %, 97,5 %) für `mean(r)`, `median(r)`, Trefferquote und
   `mean(d)`. Bei etwa 30 Clustern ist die Überdeckung grenzwertig; das wird im Bericht ausgewiesen
   (BCa optional als Robustheit).
4. **Wilson-95%-CI** für Quoten (Trefferquote, Graduation-Quoten, Basisrate):
   `(p̂ + z²/2n ± z·sqrt(p̂(1−p̂)/n + z²/4n²)) / (1 + z²/n)`, z = 1,96 – **deskriptiv** (ignoriert
   Clustering); inferenzielle Aussagen zur Trefferquote nur aus dem Cluster-Bootstrap.
5. **Sekundäre Kombinationen:** 3 Entry × 3 Exit = 9 Kombinationen, davon 1 primär; für die 8 sekundären
   werden zweiseitige Bootstrap-p-Werte `p = 2·min(F(0), 1 − F(0))` (F = empirische Verteilung des
   Bootstrap-Schätzers) berechnet und mit **Holm** korrigiert. Sekundärergebnisse ändern PASS/FAIL nie.
6. **Doppelbedingung** im Primärtest (Abschnitt 9) ist ein Intersection-Union-Test: beide Bedingungen müssen
   erfüllt sein, daher keine zusätzliche Korrektur.
7. **Mindeststichprobe:** ≥ 200 Treatment-Events **und** ≥ 30 verschiedene Devs (nach Cap).

## 9. PASS/FAIL (vorab festgelegt)

**PASS**, wenn für die Primärkombination (Entry T+30 s, Exit +5 min, S = 0,5 SOL, Priority-Fee medium,
Replay, ohne Slippage-Limit) **alle** folgenden Bedingungen gelten:

1. Das Cluster-Bootstrap-95%-CI von `mean(r)` liegt vollständig über 0 – unter **beiden**
   Graduation-Behandlungen (6.5 a und b).
2. Das Cluster-Bootstrap-95%-CI von `mean(d)` (Treatment minus gematchte Kontrollen) liegt vollständig über 0 –
   unter beiden Graduation-Behandlungen.
3. Mindeststichprobe erfüllt (≥ 200 Events, ≥ 30 Devs) und Datenqualitäts-Stopp nicht ausgelöst.

**FAIL** sonst. Bei FAIL **kein Tuning** (keine Änderung von Schwellen, Fenstern, Horizonten, Kosten oder
Ausschlüssen zur Ergebnisverbesserung); Erkenntnisse fließen in eine neue Prä-Registrierung **EXP003**.

**Underpowered:** Weniger als 200 Events oder weniger als 30 Devs nach der ersten Zählung → einmalige
Verlängerung des Analysefensters um 50 % der Fensterlänge **nach hinten** (frühere Daten; Lookback wandert
mit). Danach weiterhin unterschritten → "nicht testbar (Stichprobe)", kein PASS/FAIL.

**Datenqualitäts-Stopp:** Mehr als 5 % der Treatment-Events oder der Kontrollen sind nicht handelbar/nicht
rekonstruierbar (6.5) oder die Simulator-Validierung (6.6) scheitert → "nicht testbar (Datenqualität)",
kein PASS/FAIL.

**Paper-only:** Es wird kein Kapital eingesetzt, kein Bot gebaut, keine Order gesendet.

## 10. Datenquellen

Vergleich und Empfehlung in `docs/exp002_data_sources.md`. Default (**BEIM FREEZE FIXIEREN**, OQ-020):
primär Dune (SQL über decodierte Pump.fun-Events inkl. Reserven, `block_time`, `block_slot`, `tx_index`,
Historie ab 2024-01-14 [direkt geprüft, Spellbook-SQL]); sekundär Helius Developer für Roh-Transaktionen
zur Simulator-Validierung. Preise überwiegend NICHT VERIFIZIERT (OQ-007). Kein Kauf ohne Freigabe.

Decoder-Anforderungen: versionsfeste Event-Layouts (ältere CreateEvents ohne `creator`/`timestamp`),
Fee-Felder je Trade, Quote-Mint-Filter, Mayhem-Flag (OQ-023).

## 11. Erlaubte Vorab-Schritte und No-Peek-Erklärung

Erlaubt vor dem Freeze:

1. **Zählung** der Treatment-Events und Devs im Kandidatenfenster (ohne Renditen), um D0/D1 zu dimensionieren.
2. **Pilot** auf einem zum Analysefenster **disjunkten** Zeitraum (z. B. innerhalb des Lookback-Zeitraums
   vor D0) für Decoder-Tests und die Simulator-Validierung (6.6). Renditen aus dem Pilot dürfen keine
   Schwelle, kein Fenster und keinen Parameter dieser Prereg beeinflussen; sie werden nicht berichtet.
3. Messung der Graduation-Basisrate im Vorzeitraum (Abschnitt 12).

No-Peek-Erklärung (beim Freeze zu unterschreiben, OQ-022): Vor dem Freeze wurden keine Netto-Returns von
Launches des Analysefensters berechnet oder angesehen. Vorkenntnisse: Die Vorgänger-Session (geschlossener
PR #1 "holder-scorer") entwarf ein Pump.fun-Bewertungs- und Papier-Trading-Werkzeug; laut PR-Text waren
Solana-RPCs aus jener Umgebung nicht erreichbar, es wurden also keine realen Marktdaten ausgewertet. Die
Parameter dieser Prereg (S, Horizonte, Schwellen) sind nicht aus Daten abgeleitet.

## 12. Offener Punkt: Graduation-Basisrate (messen statt übernehmen)

Berichtete Basisraten schwanken je nach Quelle, Zeitraum und Definition zwischen etwa 0,2 % und 2,7 %;
alle Werte sind **NICHT VERIFIZIERT** (nur Snippets, Seiten gesperrt, abgerufen 2026-09-29):
0,198 % (2026-05-08 bis 2026-06-10; https://zenodo.org/records/21383616), 0,63 % (September 2025;
https://arxiv.org/html/2602.14860v1), 1,15 % (Anfang 2026;
https://www.cryptopolitan.com/pump-fun-graduating-tokens-break-to-1-15-of-new-launches/), 1,4 % (Januar 2025;
https://thedefiant.io/news/defi/pump-fun-token-graduation-rate-plummets), 2,7 % (Zeitraum unklar;
https://j.tools/en/blog/pump-fun-bonding-curve-mechanics-explained), kurzfristig 4,7–6,7 % nach der
BOOST-Änderung im Juli 2026 (https://www.theblock.co/amp/post/409815/pump-fun-token-graduation-rate-jumps-boost-changes-launch-incentives).

**Festlegung (OQ-019):** Die Basisrate wird **nicht übernommen**, sondern gemessen: Anteil aller Launches
(SOL-Quote) mit `t_complete ≤ t_create + 7 d`, ausschließlich im Zeitraum [D0 − L − 7 d, D0 − 7 d)
(point-in-time, vor dem Analysefenster), mit Wilson-95%-CI und nach Kalenderwoche aufgeschlüsselt.
Im Analysefenster wird sie nur deskriptiv erneut berichtet. Die externen Werte dienen ausschließlich als
Plausibilitätsreferenz.

## 13. Limitationen

- Dev = Wallet; Wallet-Wechsel verdünnt den Kontrast (Bias Richtung Null, konservativ). Bundles/Fremd-Wallets
  im Create-Slot nicht erkennbar (OQ-018).
- Blockzeit ist sekundengenau und geschätzt; Reihenfolge innerhalb einer Sekunde per (slot, tx_index);
  Worst-Case-Ordnung für den eigenen Fill.
- Reaktionen anderer Follower auf unsere Order sind nicht modellierbar; die Simulation ist kontrafaktisch.
- Programmänderungen 2025/2026 (dynamische Gebühren, Creator-Fee, USDC-Quote, Mayhem-Mode, Cashback/Buyback,
  negative virtuelle Quote-Reserven [direkt geprüft, Commit-Historie pump-fun/pump-public-docs]) machen
  eine zeitindexierte Behandlung von Gebühren und Kurvenparametern nötig.
- Preise der Datenquellen sind weitgehend unverifiziert (OQ-007).

## 14. Offene Punkte (nur IDs)

OQ-009, OQ-010, OQ-011, OQ-012, OQ-013, OQ-014, OQ-015, OQ-016, OQ-017, OQ-018, OQ-019, OQ-020, OQ-022,
OQ-023 – Details und Defaults in OPEN_QUESTIONS.md.

## 15. Änderungslog

| Version | Datum | Änderung |
|---|---|---|
| v0.1 DRAFT | 2026-09-29 | Erstentwurf nach Auftrag; Hypothese wörtlich übernommen; Design-Review-Fixes eingearbeitet (gereifte Dev-Historie, rollierender Lookback, Mcap-Bins, Simulator-Validierung, Graduation-Doppelbehandlung, Cluster-Bootstrap). Nicht eingefroren. |
