# Der Experte – Entscheidungsprotokoll für Edge Lab

Stand: 2026-10-03. Auftrag des Nutzers: „erstelle einen Experten, der die Entscheidungen für mich übernimmt,
aber die beste Lösung nimmt, vom Outcome."

Der Experte ist kein Programm und keine Person, sondern ein festes Protokoll, nach dem jede Claude-Code-Sitzung
in diesem Repository entscheidet, statt den Nutzer zu fragen. „Beste Lösung vom Outcome" heißt: Gewählt wird die
Option mit dem besten **später messbaren Ergebnis**, nicht die mit dem besten Eindruck heute. Jede Entscheidung
wird so protokolliert, dass sie an ihrem Ergebnis gemessen und bei Bedarf gekippt werden kann (Abschnitt 7).

Wie er benutzt wird: `CLAUDE.md` im Repo-Root verpflichtet jede Sitzung auf dieses Protokoll. Zusätzlich gibt es
den Skill `/experte <Frage>` (`.claude/skills/experte/SKILL.md`) und den Subagenten `experte`
(`.claude/agents/experte.md`) für Entscheidungen, die eine eigene Recherche brauchen. Beide werden beim Start
einer Sitzung geladen.

---

## 1. Mandat

**Der Experte entscheidet** ohne Rückfrage:

- alle Punkte in `OPEN_QUESTIONS.md` mit Status `offen`, soweit sie nicht unter die Eskalationsliste fallen;
- Parameter, Schwellen und Defaults, solange sie nicht Teil einer eingefrorenen oder vom Nutzer wörtlich
  vorgegebenen Vorregistrierung sind;
- Reihenfolge und Zuschnitt von Umbauten am Sniper und an den Auswertungen;
- ob und wie etwas gebaut wird, inklusive „nicht bauen";
- Empfehlungen zu Datenquellen und Plänen, ohne etwas zu kaufen.

**Der Experte entscheidet nie** (abschließende Liste, Eskalation an den Nutzer):

1. Geld: Käufe, Abos, Pläne, Guthaben.
2. Zugänge: API-Keys, Telegram-Account und -Session, Wallets, Logins.
3. Live-Kapital, Trading-Code, Bot-Anbindung, automatische Käufe oder Verkäufe.
4. Ausführung eines Freeze (EXP001, EXP002, EXP003) und jede Änderung an Hypothese, Metrik, Schwelle oder
   PASS/FAIL einer eingefrorenen oder vom Nutzer vorgegebenen Vorregistrierung.
5. Merge nach `main` und alles, was auf der Website oder außerhalb des Repos sichtbar wird.
6. Löschen oder Weitergabe von Aufzeichnungen und Daten Dritter (Wallet-Adressen).
7. Rechtliche und ToS-Risiken (z. B. Telegram-Scraping, OQ-021).

Bei einer Eskalation stellt der Experte die Frage mit Empfehlung und Default (Format in Abschnitt 6). Alles, was
nicht von der Antwort abhängt, läuft weiter.

---

## 2. Was „beste Lösung vom Outcome" heißt

Je Entscheidungstyp ist das Outcome-Maß fest, damit „besser" nicht nachträglich umdefiniert wird:

| Entscheidungstyp | Outcome-Maß | Woran gemessen |
|---|---|---|
| Sniper-Regel, Schwelle, Filter, Gate | Netto-Rendite der Alarme gegen gleich alte Kontroll-Token (gepaarte Differenz mit Block-Bootstrap-Intervall), auf Daten, die **nach** der Entscheidung entstanden sind | `tape report`, Primärzeile GO / +30 s / +300 s |
| Aufzeichnung, Instrumentierung, Felder in Records | Zahl der dadurch prüfbar werdenden Hypothesen je Kosten (RPC-Einheiten, Speicher, Code) | Record-/Tape-Zähler, Statuszeile, Tests |
| Reihenfolge von Umbauten | Evidenzgewinn je Aufwand: was zuerst Daten liefert, kommt zuerst | Umbau-Plan in `docs/sniper_review.md` |
| Datenquelle oder Plan (ohne Kauf) | Abdeckung der benötigten Felder, Preis je Monat, Verifikationsstand der Angaben | `docs/*_data_sources.md`, `docs/birdeye_endpoints.md` |
| Experiment-Parameter in einem Draft | Power (Mindeststichprobe), Robustheit gegen Ausreißer, keine Freiheitsgrade nach dem Blick auf Daten | Prereg-Text, OQ-Einträge |

Wo ein Outcome noch nicht messbar ist, gilt der erwartete Wert: Wahrscheinlichkeit × Nutzen minus Kosten, und
bei Gleichstand die Option, die sich leichter zurücknehmen lässt.

---

## 3. Evidenz-Rangfolge

Jede Entscheidung nennt die Stufe ihrer stärksten Evidenz:

1. Eigene Messung mit Kontrollgruppe und Intervall (Tape, Records, Zeitsplit).
2. Vorregistrierter Test mit PASS/FAIL vorab.
3. Primärquelle, am Abrufdatum geladen: **[direkt geprüft]**.
4. Offizielle Quelle nur als Suchtreffer gesehen: **[Snippet]**.
5. Kausale Schlussfolgerung aus bekannter Mechanik (Kurvenmathematik, Programmregeln).
6. Erinnerung oder Plausibilität: **NICHT VERIFIZIERT**, nie allein entscheidend.

---

## 4. Entscheidungsregeln, in dieser Reihenfolge

- **R1 Grenzen.** Die Eskalationsliste aus Abschnitt 1 und die Regel Edge-First (kein Bot-Bau, kein
  Live-Kapital, keine Käufe, keine Keys) gehen vor allem anderen.
- **R2 Erst messen, dann filtern.** Fehlt Evidenz, gewinnt die Option, die am schnellsten Evidenz erzeugt:
  aufzeichnen (record-only), dann auswerten, erst dann als Filter oder Gate einsetzen. Kein Gate ohne
  Zeitsplit-Prüfung auf späteren Daten.
- **R3 Reversibel vor irreversibel, klein vor groß.** Der Default aus `OPEN_QUESTIONS.md` gilt, solange nichts
  Stärkeres dagegen spricht.
- **R4 Kein Tuning auf dem Prüfdatensatz.** Auswahl nur auf der früheren Hälfte, Bericht auf der späteren;
  Anzahl geprüfter Varianten nennen; Holm-Korrektur bei mehreren Zeilen. „Beste Regel aus 64" ist kein Outcome.
- **R5 Nutzungsvolumen.** Keine zusätzlichen RPC-Einheiten, Dauerkosten oder Abhängigkeiten ohne messbaren
  Nutzen. Budgetgrenzen aus OQ-025 gelten.
- **R6 Gleichstand.** Weniger Code, weniger Abhängigkeiten, weniger Erklärungsbedarf gewinnt.
- **R7 Revisionsauslöser.** Jede Entscheidung nennt, welche Beobachtung sie kippt und wann sie geprüft wird.

---

## 5. Ablauf je Entscheidung

1. Frage in einem Satz.
2. Outcome-Maß nach Abschnitt 2.
3. Optionen, immer inklusive „nichts tun".
4. Evidenz je Option mit Rangstufe nach Abschnitt 3.
5. Entscheidung mit Begründung in höchstens fünf Sätzen.
6. Revisionsauslöser und Prüftermin.
7. Eintrag in `OPEN_QUESTIONS.md` (Status `entschieden (Experte)`, Datum) und eine Zeile im Outcome-Register
   (Abschnitt 7).
8. Umsetzung ohne Rückfrage. Der Nutzer erhält einen Ergebnisbericht, keine Frage.

---

## 6. Eskalation an den Nutzer – Format

> **Entscheidung nötig:** … (ein Satz)
> **Empfehlung:** … **Default, wenn keine Antwort:** …
> **Läuft bis dahin weiter:** …

---

## 7. Outcome-Register

Jede Entscheidung wird am gemessenen Ergebnis geprüft. Fällige Zeilen werden bei jedem `tape report` und bei
jeder Prereg-Auswertung nachgetragen. Fällt das Ergebnis schlechter aus als erwartet, wird der OQ-Eintrag wieder
geöffnet und die Entscheidung mit Datum revidiert.

| ID | Datum | Entscheidung | Erwartetes Outcome | Prüftermin | Gemessenes Outcome | Lehre |
|---|---|---|---|---|---|---|
| E-001 | 2026-10-03 | Narrativ-Welle als 0.3.3 bauen, record-only, kein Gate (OQ-028) | Wellen-Rang und Themen-Zufluss stehen in jedem Record; nach ≥ 200 Alarmen ist prüfbar, ob Wellen-Erste besser rentieren als Kontrollen | nach 200 Alarmen aus ≥ 30 Stunden | – | – |
| E-002 | 2026-10-03 | Profil-Gate: Halter-Anstieg aktiv, Profil erst nach bestandener Zeitsplit-Prüfung (OQ-027) | weniger GO auf stehende Coins; keine Verschlechterung der Primärzeile gegenüber Kontrollen | erster `tape report` mit ≥ 100 GO | – | – |
| E-003 | 2026-10-03 | Sniper-Betrieb: Stufe 1, Budget 1000 je Stunde, Papier-Latenz 30 s (OQ-025) | ≤ 1 Mio. RPC-Einheiten je Monat; Handy-Nachrichten unter 30 je Stunde | nach 7 Tagen Betrieb (Statuszeile, Helius-Dashboard) | – | – |
| E-004 | 2026-10-03 | EXP003-Prereg-Entwurf erst ab 200 Alarmen aus 30 Stunden; bis dahin keine Regeländerung aus Papier-Reports (OQ-026) | kein Tuning auf den Prüfdaten | bei Erreichen der Stichprobe | – | – |
| E-005 | 2026-10-03 | Externe Narrativ-Quellen: Telegram-Mitleser erst nach EXP001-Freeze und nur record-only; DexScreener-Boosts erst nach [direkt geprüft]; X-API nein | keine neuen Kosten, keine ToS-Risiken vor Freigabe | mit EXP001-Freeze | – | – |
| E-006 | 2026-10-03 | Birdeye: vor jedem Kauf ein Free-Tier-Pilot mit ~20 Events zur Abdeckungsprüfung der Pump.fun-Kurve (OQ-005/006) | Kaufentscheidung erst mit geprüfter Abdeckung und gemessenen CU/Call | nach dem Pilot | – | – |
| E-007 | 2026-10-03 | EXP002-Draft-Parameter (OQ-009 bis OQ-017) gelten als Entscheidung für v0.1.1; Fixierung beim Freeze bleibt Nutzer | Draft ist freeze-fähig ohne weitere Rückfragen | beim Freeze | – | – |
| E-008 | 2026-10-03 | Creator-Fee je beobachtetem Coin im `tape report` (Untergrenze aus den protokollierten Gebührenfeldern) als Datengrundlage für OQ-029 | vor jeder Launch-Entscheidung liegt die Verteilung vor, was Launches in ihren ersten Minuten an Gebühr abwerfen | erster `tape report` mit ≥ 100 Coins | – | – |
| E-009 | 2026-10-03 | DexScreener-Bezahlsignale record-only messen (`dex beobachten`/`dex report`), keine Boosts kaufen (OQ-030) | Follower-Rendite nach Boost/„Dex paid" liegt mit Intervall vor; Erwartung aus der Evidenz: ≤ 0 | ≥ 200 Ereignisse aus ≥ 30 Stunden | – | – |
| E-010 | 2026-10-04 | Launch-Rechner (`launch rechner`) und Fair-Launch-Anleitung (`docs/fair_launch.md`) als Wissensgrundlage für OQ-029; die Kapitalentscheidung bleibt Eskalation | der Nutzer entscheidet mit Zahlen (Dev-Anteil, Fremdzufluss, Teilverkauf, Impact) statt mit Gefühl | bei einer Launch-Entscheidung des Nutzers | – | – |

---

## 8. Erste Entscheidungen im Detail (2026-10-03)

**E-001 Narrativ-Welle (OQ-028).** Frage: Soll der Sniper die Launch-Welle eines Themas erkennen und als
frühe Narrativ-Information nutzen? Outcome-Maß: Rendite der Alarme in Wellen-Rang 1 gegen Kontrollen.
Optionen: nichts tun; bauen als Gate; bauen record-only mit Zeile in der Nachricht. Evidenz: Stufe 5
(Mechanik: Copycat-Deployer reagieren in Sekunden auf einen Auslöser, ihre Welle verrät das Thema vor jedem
Handelsdatum), keine eigene Messung. Entscheidung: record-only bauen, null zusätzliche RPC-Last, Zeile
`Them …` in BLICK/GO, Feld `narrativ` im Record und im Papier-Kontext (R2, R5). Kein Gate, bis ein Zeitsplit
zeigt, dass Wellen-Rang Rendite trennt (R2, R4). Revisionsauslöser: Nach 200 Alarmen keine Differenz zwischen
Rang 1 und Kontrollen → Zeile bleibt informativ, kein weiterer Ausbau; Differenz vorhanden → Gate mit
Zeitsplit-Prüfung wie beim Profil.

**E-002 Profil-Gate (OQ-027).** Halter-Anstieg folgt direkt aus dem Befund „Score misst Alter, nicht
Qualität" (Stufe 5) und kostet nichts; bleibt aktiv. Das Ähnlichkeitsprofil wird erst geladen, wenn
`profil bauen --split 0.5` ein Bootstrap-Intervall > 0 meldet (R2). Schwellen bleiben, bis 200 Alarme vorliegen.

**E-003 Betrieb (OQ-025).** Stufe 1, Budget 1000, Latenz 30 s: einzige Kombination, die Free-Tarif und ein
Handy zugleich aushalten (Stufe 5, Rechenmodell im README). Kippt, wenn die Statuszeile mehr als
1 000 Einheiten je Stunde zeigt oder weniger als 5 GO am Tag kommen.

**E-004 Erfolgsmaß (OQ-026).** Papier-Reports wählen die beste von vielen Regeln; daraus Regeln abzuleiten
wäre Tuning auf dem Prüfdatensatz (R4). Erst Stichprobe, dann Prereg EXP003, dann Auswertung.

**E-005 Externe Quellen.** Telegram ist Hypothese von EXP001; sie vorab im Sniper zu nutzen würde den Test mit
sich selbst prüfen und trägt ToS-Risiko (Eskalationspunkt 7). DexScreener und X scheitern an Verifikation bzw.
Geld (Eskalationspunkt 1).

**E-006 Birdeye.** Kauf ist Eskalationspunkt 1. Was der Experte entscheiden kann: Der kostenlose Pilot kommt
vor jeder Kaufempfehlung, weil die Abdeckung der Pump.fun-Kurve durch Birdeye NICHT VERIFIZIERT ist.

**E-007 EXP002-Parameter.** Die Defaults der OQ-009 bis OQ-017 stehen im Draft; sie gelten damit als
entschieden, bis der Nutzer den Freeze bestätigt. Der Freeze selbst bleibt Eskalationspunkt 4.

**E-008 Creator-Seite messen (OQ-029).** Die Frage „eigener Launch zum Profit" ist Eskalation (Geld, Live-Kapital,
Recht). Was der Experte entscheiden kann: Bevor Kapital fließt, liefert das eigene Tape die Verteilung der
Creator-Fee je Coin in den ersten Minuten (Feld `creator_fee` jedes Trades, R2, R5). Erwartung aus der Mechanik:
Bei 0,30 % des Kurvenvolumens und einer Graduation-Rate um 1 % verdient die große Mehrheit der Launches auf der
Kurve nahezu nichts; Gebühren nach der Graduation (PumpSwap) sind im Tape nicht enthalten.

**E-009 DexScreener-Bezahlsignale (OQ-030).** Frage: Wie kann Edge Lab von Boosts und „Dex paid" profitieren?
Optionen: Boosts als Creator kaufen (Geld, und ohne Verkauf des eigenen Bestands in die Käufer nie tragfähig, siehe
`docs/dexscreener_paid.md` Abschnitt 5); Signale als Follower handeln (ungeprüft, einzige Studie negativ);
Signale messen (kostenlos, ohne Schlüssel, R2); nichts tun. Entscheidung: messen. Die Feeds sind öffentlich, die
Preise frei abrufbar, der Aufwand liegt bei einer Anfrage je Minute. Revisionsauslöser: Bootstrap-Intervall der
Follower-Rendite bei ≥ 200 Ereignissen; unter 0 → Signal wird als Warnhinweis in den Sniper aufgenommen (nach
eigener Zeitsplit-Prüfung), über 0 → Prereg EXP004.

Nicht entscheidbar (bleiben `offen`, Eskalation): OQ-001 (Datei fehlt), OQ-002 (Abgleich mit dem Prereg-Text
braucht die Datei), OQ-008 (Veröffentlichung im Pages-Repo = Eskalationspunkt 5), OQ-020 (Kauf), OQ-021
(ToS), OQ-024 (nur der Nutzer hat die Logs), OQ-029 (eigener Launch: Geld, Live-Kapital, Recht).
