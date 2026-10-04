# Kanal-Discovery (EXP001 Anhang A) – Setup und Ablauf

Skript: `scripts/channel_discovery.py`. Stand: 2026-09-29. Das Skript wurde in der Erstellungsumgebung
**nicht ausgeführt** (kein Netzzugang zu Telegram, keine Credentials) und ist ein Gerüst, das am
Stichtag von dir gestartet wird. Regeln: Edge-First, kein Bot-Bau, keine Käufe, **keine API-Keys im Repo**.

## 1. Was das Skript tut (Kriterium A.1)

Am Stichtag werden die Top-50 Telegram-Broadcast-Kanäle nach einem vorab festgelegten Kriterium
ermittelt (Nutzerentscheidung 2026-09-29; Abgleich mit Anhang A der Prereg offen, siehe
OPEN_QUESTIONS.md OQ-002/OQ-003):

1. Suche mit der festen Keyword-Liste im Skript (`KEYWORDS`) über `contacts.search`.
2. Nur Broadcast-Kanäle (keine Gruppen/Megagroups, keine Nutzer/Bots), Dedupe nach Kanal-ID.
3. Je Kanal Abonnentenzahl (`participants_count`) und Flags über `channels.getFullChannel`, letzter
   regulärer Post über die Nachrichtenhistorie.
4. Aktiv = mindestens ein Post ab Stichtag 00:00 UTC minus 7 Tage bis zum Abrufzeitpunkt (der Lauf erfolgt am
   Stichtag selbst; ein späterer Lauf mit `--date` in der Vergangenheit würde auch spätere Posts mitzählen).
5. Ranking nach Abonnenten absteigend (Tiebreak Kanal-ID), Top-50. Scam-/Fake-/Restricted-Flags werden
   protokolliert, nicht gefiltert.

Ausgaben (alle in `data/`):

- `channels_<YYYY-MM-DD>.csv` – die Top-50 (kanonische Datei für die Prereg),
- `channels_<YYYY-MM-DD>_raw.csv` – alle Kandidaten mit Ausschlussgrund/Fehler (Audit),
- `channels_<YYYY-MM-DD>.meta.json` – Parameter, Kriterium-Hash (`criterion_sha256` über Keywords und
  Parameter), Keyword-Hash (`keywords_sha256`, nur die Liste), Zähler, Fehler, SHA-256 der CSVs und des Skripts,
  Telethon-Version und TL-Layer.

Telegram bietet keine offizielle globale "Top-Kanäle"-Liste; die verfügbaren Methoden sind Suche
(`contacts.search`, `messages.searchGlobal`), eigene Top-Peers und Kanal-Empfehlungen (direkt geprüft über
die Methodenbeschreibungen im gotd/td-Repo, abgerufen 2026-09-29, z. B.
https://raw.githubusercontent.com/gotd/td/main/tg/tl_contacts_search_gen.go und
https://raw.githubusercontent.com/gotd/td/main/tg/tl_channels_get_channel_recommendations_gen.go).
`contacts.search` liefert pro Anfrage nur wenige Treffer (Telethon-Issue #1431,
https://github.com/LonamiWebs/Telethon/issues/1431, abgerufen 2026-09-29) und ist zeitlich instabil.
Die Discovery ist deshalb ein **Snapshot am Stichtag**, reproduzierbar über CSV + meta.json + Hash, nicht
über Wiederholung der Suche.

## 2. Warum Telethon (und nicht Pyrogram)

Alle Angaben direkt geprüft am 2026-09-29 (PyPI-JSON bzw. GitHub):

| Bibliothek | Letztes Release | Status | Quelle |
|---|---|---|---|
| **Telethon** | 1.45.0 (2026-09-10); davor 1.44.0 (2026-06-15), 1.43.2 (2026-04-20) | aktiv gepflegt; Entwicklung auf Codeberg (GitHub-Repo am 2026-02-21 archiviert, README: "Moved to https://codeberg.org/Lonami/Telethon") | https://pypi.org/pypi/Telethon/json ; https://github.com/LonamiWebs/Telethon |
| Pyrogram | 2.0.106 (2023-04-30) | Repo am 2024-12-23 archiviert, README: "no longer maintained" | https://pypi.org/pypi/Pyrogram/json ; https://github.com/pyrogram/pyrogram |
| kurigram (Pyrogram-Fork) | 2.2.26 (2026-09-12) | aktiv | https://pypi.org/pypi/kurigram/json |
| pyrofork (Pyrogram-Fork) | 2.3.69 (2025-12-10) | Repo am 2026-09-14 archiviert | https://pypi.org/pypi/pyrofork/json ; https://github.com/Mayuri-Chan/pyrofork |

Entscheidung: **Telethon**, gepinnt auf `1.45.0`. Gründe: Original-Projekt mit laufenden Releases, direkter
Zugriff auf die Roh-API (`functions.contacts.SearchRequest`, `functions.channels.GetFullChannelRequest`),
stabile Dokumentation (docs.telethon.dev), reine Python-Abhängigkeiten (`pyaes`, `rsa`;
https://raw.githubusercontent.com/LonamiWebs/Telethon/v1/setup.py). Pyrogram selbst ist eingestellt;
die Forks sind gepflegt, aber fragmentiert.

## 3. Voraussetzungen

- Python 3.11 oder neuer (Skript nutzt nur Standardbibliothek + Telethon).
- Ein **etablierter** Telegram-User-Account (kein frischer Account, keine VoIP-Nummer). `contacts.search`
  ist nur für User-Accounts verfügbar, nicht für Bots (Telethon `methods.csv`,
  https://raw.githubusercontent.com/LonamiWebs/Telethon/v1/telethon_generator/data/methods.csv,
  abgerufen 2026-09-29). Die Telethon-FAQ warnt, dass Drittanbieter-Bibliotheken bei neuen Accounts oder
  missbräuchlicher Nutzung zu Sperren führen können
  (https://raw.githubusercontent.com/LonamiWebs/Telethon/v1/readthedocs/quick-references/faq.rst).
- Telegram-API-Terms (Kopie via Open Terms Archive, Stand 2026-07-02,
  https://raw.githubusercontent.com/OpenTermsArchive/contrib-versions/main/Telegram/Developer%20Terms.md):
  u. a. 1.4 keine Aktionen ohne Wissen und Zustimmung des Nutzers, 2.1 eigene `api_id`. Das Skript liest
  nur öffentliche Kanalmetadaten, tritt nichts bei und sendet nichts.

## 4. Credentials (nie ins Repo)

1. Auf https://my.telegram.org mit der Telefonnummer des Accounts einloggen.
2. "API development tools" öffnen, eine Anwendung anlegen (App title, Short name; URL nicht nötig).
3. `api_id` und `api_hash` notieren. Der `api_hash` kann nicht widerrufen werden und darf nirgends
   veröffentlicht werden (Telegram sperrt veröffentlichte IDs: Fehler `API_ID_PUBLISHED_FLOOD`, "This API id was
   published somewhere, you can't use it now" [direkt geprüft: Telethon errors.csv,
   https://raw.githubusercontent.com/LonamiWebs/Telethon/v1/telethon_generator/data/errors.csv, abgerufen 2026-09-29]).
   Quelle der Schritte: Telethon-Doku "Signing In",
   https://raw.githubusercontent.com/LonamiWebs/Telethon/v1/readthedocs/basic/signing-in.rst (abgerufen 2026-09-29);
   die offizielle Seite https://core.telegram.org/api/obtaining_api_id war aus der Arbeitsumgebung nicht
   abrufbar.
4. Als Umgebungsvariablen setzen (nur in der Shell, nicht in Dateien im Repo):

```bash
export TG_API_ID=123456            # Beispielformat, eigener Wert
export TG_API_HASH=...             # eigener Wert, geheim
export TG_SESSION=.secrets/edge_lab.session   # optional; Default wie hier
```

`.secrets/`, `*.session`, `*.session-journal` und `.env` stehen in `.gitignore`.

## 5. Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install telethon==1.45.0
# optional, schnellere Kryptografie: pip install cryptg
```

## 6. Probelauf ohne Netz

```bash
python3 -m py_compile scripts/channel_discovery.py
python3 scripts/channel_discovery.py --dry-run
python3 -m unittest scripts/tests/test_channel_discovery.py   # 10 Tests mit Fake-Client, kein Netz
```

Der Dry-Run gibt Konfiguration, Aktivitäts-Cutoff, geplante Ausgabepfade, das Request-Budget und den
Status der Umgebungsvariablen (nur vorhanden/nicht vorhanden) aus. Er schreibt nichts und importiert
Telethon nicht.

## 7. Erstlogin und Lauf am Stichtag

```bash
python3 scripts/channel_discovery.py --date 2026-10-15
```

- Beim ersten Start fragt Telethon interaktiv nach Telefonnummer, Login-Code und – falls aktiv – dem
  2FA-Passwort (`client.start()`, Quelle:
  https://raw.githubusercontent.com/LonamiWebs/Telethon/v1/telethon/client/auth.py). Danach liegt die
  Session-Datei unter `TG_SESSION` (SQLite; Default `.secrets/edge_lab.session`, Rechte 600). Wer diese
  Datei besitzt, kann den Account nutzen – niemals teilen oder committen.
- Nicht dieselbe Session parallel auf zwei Rechnern verwenden (`AUTH_KEY_DUPLICATED`).
- FloodWait: Telethon meldet `FloodWaitError` mit Wartezeit. Bis 300 s wartet das Skript und wiederholt
  den Aufruf einmal; darüber bricht es ab (Exit 3) und schreibt **keine** kanonischen Dateien. Zwischen
  Aufrufen pausiert es 1,5 s (`--sleep`).
- `--date` ist der Stichtag (UTC). Der Aktivitäts-Cutoff ist Stichtag 00:00 UTC minus 7 Tage.
- `--top`, `--keywords-file` und `--with-global-search` verändern das Kriterium. Das Skript markiert
  solche Läufe als `A.1-custom-<hash>`; sie sind für den Freeze **nicht** verwendbar und dienen nur
  Tests.

## 8. Nach dem Lauf

1. `data/channels_<datum>.csv`, `data/channels_<datum>_raw.csv` und `data/channels_<datum>.meta.json`
   prüfen (Zähler, Fehlerliste, `freeze_capable: true`).
2. Die drei Dateien committen. Der SHA-256 der Top-CSV steht in meta.json; er ist Teil des
   EXP001-Freeze-Artefakts (siehe FREEZE_CHECKLIST.md).
3. Keine manuelle Nachbearbeitung der CSV.

## 9. Bekannte Grenzen

- `contacts.search` deckt nur einen Teil der Kanäle ab und ist nicht erschöpfend (Issue #1431). Der
  Recall hängt an der Keyword-Liste; sie ist Teil des Kriteriums und darf nach dem Freeze nicht
  geändert werden.
- `participants_count` ist ein optionales Feld (Flag-Feld des Typs `channelFull` [direkt geprüft:
  https://raw.githubusercontent.com/gotd/td/main/tg/tl_chat_full_gen.go, abgerufen 2026-09-29]; Telethon 1.45.0:
  `types.ChannelFull.participants_count: Optional[int] = None`); fehlt es, steht der Kanal am Ende des Rankings
  (Zähler `participants_count_missing` in meta.json). Entscheidung dazu: OQ-003.
- `contacts.search` bietet in TL-Layer 229 die Flags `broadcasts`/`bots` (Telethon 1.45.0: `SearchRequest(q, limit,
  broadcasts=None, bots=None)`, per Introspektion geprüft). Das Skript setzt sie bewusst nicht, weil die
  Server-Semantik nicht verifiziert werden konnte; eine Übernahme wäre Kriterium A.2 (OQ-002).
- Kanäle, deren Historie nicht lesbar ist (restricted/privat), werden als "activity_unknown" oder
  "error" ausgeschlossen und in der Roh-CSV geführt.
- Drittanbieter-Verzeichnisse (TGStat: Suche nur in Bezahlplänen, rtgstat-README
  https://raw.githubusercontent.com/selesnow/rtgstat/master/README.md; Telemetr.io: API-Free-Plan
  1 000 Requests/Monat laut Bellingcat-Toolkit https://raw.githubusercontent.com/bellingcat/toolkit/main/gitbook/tools/telemetrio/README.md,
  beide abgerufen 2026-09-29) wurden als Alternative geprüft, aber nicht gewählt (zusätzlicher Anbieter,
  Kosten, Nutzerentscheidung 2026-09-29).
