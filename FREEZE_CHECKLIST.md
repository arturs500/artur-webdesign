# FREEZE_CHECKLIST – EXP001 Prereg v0.3

Stand: 2026-09-29. Diese Liste beschreibt, was für den Freeze von `PREREGISTRATION_EXP001.md` v0.3
erledigt ist, was fehlt, und die exakten Befehle. **Der Freeze wird nicht ohne ausdrückliche Bestätigung
des Nutzers ausgeführt.**

## 1. Erledigt (2026-09-29)

- [x] `docs/birdeye_endpoints.md`: OHLCV-V3-Endpoints, Parameter, Intervalle, Limits, CU-Anker, Rate-Limits,
      Pläne/Preise mit Quellen und Kennzeichnung; parametrische CU-Rechnung für ≥ 200 Events × 1 h inkl.
      Baselines; Plan-Empfehlung (Lite) ohne Kauf.
- [x] `scripts/channel_discovery.py`: Gerüst (Telethon 1.45.0) für Anhang A, Kriterium A.1, schreibt
      `data/channels_<datum>.csv`, `data/channels_<datum>_raw.csv`, `data/channels_<datum>.meta.json`;
      nicht ausgeführt; `--dry-run` und `py_compile` geprüft.
- [x] `scripts/README_channel_discovery.md`: Setup, Credentials (api_id/api_hash), Erstlogin, ToS-/FloodWait-
      Hinweise, Ablauf am Stichtag, Begründung Telethon vs. Pyrogram.
- [x] `data/.gitkeep`; `.gitignore` um Sessions/Secrets/Python-Artefakte ergänzt.
- [x] `OPEN_QUESTIONS.md` mit allen Unklarheiten (OQ-001 … OQ-023).
- [x] Phase B: `PREREGISTRATION_EXP002.md` (DRAFT), `docs/exp002_data_sources.md`.

## 2. Fehlt / Blocker

| # | Blocker | Bezug | Nötig für Freeze? |
|---|---|---|---|
| 1 | **`PREREGISTRATION_EXP001.md` v0.3 liegt nicht im Repository** (weder Arbeitsbaum noch Historie). Ohne Datei kein Freeze und kein Hash. | OQ-001 | ja |
| 2 | Anhang-A-Kriterium A.1 (Keywords, Aktivitätsfenster 7 Tage, Broadcast-only, Top-50, Ranking nach Abonnenten) muss mit dem Text in Anhang A der Prereg abgeglichen werden; Prereg soll auf `scripts/channel_discovery.py` und `criterion_version = "A.1"` verweisen. | OQ-002, OQ-003 | ja |
| 3 | Baseline-Definition und Horizonte für die CU-Rechnung bestätigen (k, Pre-Window, weitere Horizonte). | OQ-004 | ja, falls Birdeye Datenquelle der Prereg ist |
| 4 | Birdeye: CU pro OHLCV-Call, 1m-Retention und Abdeckung der Pump.fun-Kurve verifizieren (Free-Tier-Pilot ca. 20 Events, Credits-Usage-Endpoint). | OQ-005 | ja, falls Birdeye Datenquelle der Prereg ist |
| 5 | Birdeye-Plan-Entscheidung (Empfehlung Lite, 39 USD) – nur Entscheidung, kein Kauf im Auftrag. | OQ-006 | nein (nach Freeze) |
| 6 | Direktverifikation der [Snippet]-Zahlen nach Freigabe der gesperrten Hosts. | OQ-007 | ja, soweit die Prereg auf diesen Zahlen aufbaut |
| 7 | Entscheidung zur Ablage im Website-Repo (GitHub Pages/Jekyll) vor einem Merge nach `main`. | OQ-008 | nein (Freeze auf Branch möglich) |

## 3. Prüfungen unmittelbar vor dem Freeze (alle müssen erfüllt sein)

- [ ] `PREREGISTRATION_EXP001.md` liegt im Repo; Header trägt `Version: v0.3`, Status und Datum.
- [ ] Gegenüber der letzten vom Nutzer freigegebenen Fassung wurden **keine** Hypothese, Metrik, Schwelle
      oder PASS/FAIL-Regel geändert (`git diff` der Datei zeigt nur redaktionelle/Anhang-Änderungen).
- [ ] Anhang A verweist auf `scripts/channel_discovery.py`, Kriterium A.1 und die Keyword-Liste; die
      Keyword-Liste im Skript entspricht Anhang A.
- [ ] No-Peek-Attest: vor dem Freeze wurden keine Ergebnisdaten des Analysefensters ausgewertet.
- [ ] `OPEN_QUESTIONS.md` ist aktuell; alle Einträge, die den EXP001-Freeze blockieren, sind `entschieden`.
- [ ] `git status` ist sauber (keine ungewollten Dateien, keine `.session`/`.env`), Branch korrekt.
- [ ] Keine API-Keys oder api_hash-Werte im Diff (`git grep -n -E "api_hash *= *['\"][A-Za-z0-9]" -- ':!*.md'` leer).

## 4. Exakte Befehle für den Freeze (vom Nutzer vorgegeben, unverändert)

Auf dem vorgesehenen Branch, im Repo-Root:

```bash
git add -A && git commit -m "EXP001 prereg v0.3 FROZEN"
shasum -a 256 PREREGISTRATION_EXP001.md > PREREGISTRATION_EXP001.sha256
```

Hinweise zu den Befehlen (Zusatz, nicht Teil der vorgegebenen Befehle):

- Die `.sha256`-Datei entsteht nach dem Freeze-Commit und wird in einem **separaten** Folge-Commit
  eingecheckt (z. B. `git add PREREGISTRATION_EXP001.sha256 && git commit -m "EXP001 prereg v0.3 sha256"`).
- `shasum` ist das macOS-/Perl-Werkzeug; unter Linux liefert `sha256sum PREREGISTRATION_EXP001.md`
  denselben Hash im gleichen Format.
- Optionaler Zusatzvorschlag, da Anhang A Teil der Prereg ist:
  `shasum -a 256 scripts/channel_discovery.py >> PREREGISTRATION_EXP001.sha256`
- Der Datei-Hash sichert den Inhalt; ein Tag sichert zusätzlich den Commit:
  `git tag -a exp001-v0.3-frozen -m "EXP001 prereg v0.3 frozen"` (optional).
- Nach dem Freeze: keine Änderungen an Hypothese, Metriken, Schwellen oder PASS/FAIL. Ergänzungen nur
  als Addendum mit neuer Versionsnummer und Änderungslog.

## 5. Status

**FREEZE NICHT AUSGEFÜHRT.** Blocker #1 (Datei fehlt) ist offen. Freeze erst nach Bestätigung des Nutzers.
