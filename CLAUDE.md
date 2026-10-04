# Edge Lab – Arbeitsregeln für Claude Code in diesem Repository

Sprache: Deutsch. Das Repo ist zugleich die GitHub-Pages-Website (`index.html`, `CNAME`); die Edge-Lab-Dateien
liegen im Root, in `docs/`, `scripts/`, `tools/holder-scorer/` (siehe OQ-008 zur Veröffentlichung).

## Regel Edge-First (vom Nutzer vorgegeben)

Kein Bot-Bau, kein Live-Kapital, keine Käufe oder Abos, keine API-Keys im Repo. Fakten (Endpoints, Preise,
Limits) nur mit Quellen-URL und Abrufdatum, gekennzeichnet als **[direkt geprüft]**, **[Snippet]** oder
**NICHT VERIFIZIERT**; nichts aus dem Gedächtnis. Unklarheiten in `OPEN_QUESTIONS.md` notieren statt raten.

## Entscheidungen trifft der Experte

Offene Fragen entscheidet die Sitzung selbst nach `docs/experte.md` (Outcome-Maß, Evidenz-Rangfolge, Regeln
R1–R7, Outcome-Register). Den Nutzer nur bei der Eskalationsliste fragen: Geld, Zugänge/Keys, Live-Kapital
oder Trading-Code, Ausführung eines Freeze oder Änderung einer Prereg-Hypothese/-Metrik/-Schwelle, Merge nach
`main`/Veröffentlichung, Löschen oder Weitergabe von Daten, ToS-/Rechtsrisiken. Eskalationsformat: Frage,
Empfehlung, Default, was weiterläuft. Jede Entscheidung als Eintrag in `OPEN_QUESTIONS.md` mit Status
`entschieden (Experte)` und als Zeile im Outcome-Register; fällige Zeilen bei jedem `tape report` nachtragen.

Nie ohne ausdrückliches „Go" des Nutzers: `FREEZE_CHECKLIST.md` ausführen, Dateien löschen, nach `main` mergen.

## Arbeitsweise

- Branch `claude/zen-edison-a9sheo`, Draft-PR #2; Commits deutsch, mit Attribution-Footer der Sitzung.
- Keine Liquid-Syntax in Markdown-Dateien, also keine doppelten geschweiften Klammern und kein Klammer-Prozent
  (Jekyll, OQ-008); vor dem Commit mit grep prüfen.
- Keine Secrets, keine `.jsonl`-Aufzeichnungen, keine `.session`-Dateien committen (`.gitignore`).
- Sniper-Tests: `cd tools/holder-scorer && python -m pytest -q` (offline, ohne Netz).
- Nutzungsvolumen sparsam: keine neuen RPC-Aufrufe im Live-Betrieb ohne messbaren Nutzen (OQ-025).
- Jede Regeländerung am Sniper ist eine Hypothese: zuerst aufzeichnen (Record, Tape), dann mit `tape report`
  gegen Kontrollen messen, erst dann filtern (R2 in `docs/experte.md`).

## Einstieg

`docs/sniper_review.md` (Analyse und Umbau-Plan), `tools/holder-scorer/README.md` (Betrieb),
`PREREGISTRATION_EXP002.md`, `FREEZE_CHECKLIST.md`, `OPEN_QUESTIONS.md` (alle offenen Punkte mit IDs).
