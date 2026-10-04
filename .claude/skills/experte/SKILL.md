---
name: experte
description: Entscheidungsprotokoll des Edge-Lab-Experten anwenden (docs/experte.md) – eine offene Frage nach messbarem Outcome entscheiden, in OPEN_QUESTIONS.md und im Outcome-Register protokollieren und umsetzen, statt den Nutzer zu fragen. Nutzen bei "soll ich …", bei OQ-Defaults, Parameterwahl, Umbau-Reihenfolge.
---

# /experte – eine Entscheidung treffen

Eingabe: die Frage (Argument), sonst die offenen Punkte in `OPEN_QUESTIONS.md`.

1. `docs/experte.md` lesen (Mandat, Outcome-Maße, Evidenz-Rangfolge, Regeln R1–R7, Checkliste).
2. Prüfen, ob die Frage unter die Eskalationsliste fällt (Geld, Zugänge, Live-Kapital/Trading-Code, Freeze
   oder Prereg-Kern, Merge/Veröffentlichung, Löschen/Weitergabe, ToS/Recht). Wenn ja: Eskalation im Format aus
   Abschnitt 6 formulieren und alles weiterführen, was nicht von der Antwort abhängt.
3. Sonst die Checkliste aus Abschnitt 5 abarbeiten: Frage in einem Satz, Outcome-Maß, Optionen inklusive
   „nichts tun", Evidenz je Option mit Rangstufe, Entscheidung mit Begründung in höchstens fünf Sätzen,
   Revisionsauslöser mit Prüftermin.
4. Protokollieren: OQ-Eintrag in `OPEN_QUESTIONS.md` (neuer Eintrag oder Status des bestehenden auf
   `entschieden (Experte)` mit Datum), Zeile im Outcome-Register in `docs/experte.md`.
5. Umsetzen ohne Rückfrage, Tests laufen lassen, committen und pushen wie in `CLAUDE.md` beschrieben.
6. Dem Nutzer berichten: Entscheidung, Begründung, was gebaut wurde, Revisionsauslöser. Keine Frage am Ende.

Für Entscheidungen, die eine eigene Recherche im Repo brauchen, den Subagenten `experte` mit der Frage
starten und sein Ergebnis übernehmen.
