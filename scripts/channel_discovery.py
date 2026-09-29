#!/usr/bin/env python3
"""
channel_discovery.py – Edge Lab, EXP001 Anhang A (Kanal-Discovery), Kriterium A.1.

Zweck
-----
Listet am Stichtag die Top-50 Telegram-Broadcast-Kanäle nach einem VORAB festgelegten Kriterium auf
und schreibt sie reproduzierbar als CSV (plus Roh-CSV und meta.json mit SHA-256) nach data/.

Kriterium A.1 (fix, Teil der Prä-Registrierung; Nutzerentscheidung 2026-09-29, siehe OPEN_QUESTIONS.md
OQ-002/OQ-003):
  1. Suche mit der festen Keyword-Liste KEYWORDS über die Telegram-Methode contacts.search
     (Telethon: functions.contacts.SearchRequest, limit = SEARCH_LIMIT je Keyword). Die Flags
     broadcasts/bots von contacts.search (TL-Layer 229) werden bewusst NICHT gesetzt: Server-Semantik nicht
     verifiziert; eine Übernahme wäre Kriterium A.2 (OPEN_QUESTIONS.md OQ-002).
  2. Nur Broadcast-Kanäle (types.Channel mit broadcast=True und megagroup=False); Nutzer, Bots,
     Gruppen und Megagroups werden verworfen. Dedupe nach channel_id.
  3. Je Kanal channels.getFullChannel -> participants_count (Abonnenten) und Flags; letzter regulärer
     Post (keine Service-Nachricht) über die Nachrichtenhistorie.
  4. Aktiv = mindestens ein Post ab (Stichtag 00:00 UTC − ACTIVE_WITHIN_DAYS Tage) bis zum Abrufzeitpunkt
     (der Lauf erfolgt am Stichtag selbst).
  5. Ranking: participants_count absteigend, Tiebreak channel_id aufsteigend; Kanäle ohne
     participants_count ans Ende (werden gezählt, nicht gefiltert). Top TOP_N.
  Scam-/Fake-/Restricted-Flags werden protokolliert, NICHT gefiltert (OQ-003).

Dieses Skript ist ein GERÜST und wurde in der Erstellungsumgebung NICHT gegen Telegram ausgeführt
(kein Netz, keine Credentials). Vor dem Stichtag: Probelauf mit --dry-run, dann ein Testlauf mit
kleiner Keyword-Liste (--keywords-file), der als "custom" markiert wird und nicht freeze-fähig ist.

Bibliothek: Telethon (gepinnt auf TELETHON_PIN). Begründung siehe README_channel_discovery.md.

Credentials ausschließlich über Umgebungsvariablen (nie im Repo):
  TG_API_ID, TG_API_HASH  – von https://my.telegram.org ("API development tools")
  TG_SESSION              – Pfad der Telethon-Session-Datei (Default .secrets/edge_lab.session)

Nutzung
-------
  python3 scripts/channel_discovery.py --dry-run
  python3 scripts/channel_discovery.py --date 2026-10-15
  python3 scripts/channel_discovery.py --date 2026-10-15 --out-dir data --sleep 1.5

Exit-Codes: 0 ok, 1 Konfigurationsfehler, 2 fehlende Credentials/Bibliothek, 3 Lauf abgebrochen
(z. B. FloodWait > FLOOD_WAIT_MAX_SECONDS) – dann werden KEINE kanonischen Ausgabedateien geschrieben.

Regeln des Projekts: Edge-First, kein Bot-Bau, keine Käufe, keine API-Keys im Repo. Dieses Skript liest
nur öffentliche Kanalmetadaten; es tritt keinem Kanal bei und sendet keine Nachrichten.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Optional

# ----------------------------------------------------------------------------------------------------
# Kriterium A.1 – FIXE Parameter (Änderung = neues Kriterium, siehe criterion_version-Logik unten)
# ----------------------------------------------------------------------------------------------------
CRITERION_VERSION = "A.1"

# Feste Keyword-Liste (Reihenfolge ist Teil des Kriteriums; Hash steht in meta.json).
# Hinweis: Telegram meldet QUERY_TOO_SHORT bei zu kurzen Suchbegriffen (Mindestlänge offiziell nicht
# verifiziert); zu kurze Keywords werden protokolliert und übersprungen.
KEYWORDS: tuple[str, ...] = (
    "solana",
    "solana gems",
    "solana calls",
    "solana alpha",
    "pump.fun",
    "pumpfun",
    "pump fun",
    "memecoin",
    "meme coin",
    "meme coins",
    "gem calls",
    "crypto calls",
    "alpha calls",
    "degen calls",
    "sniper calls",
    "100x gems",
)

TOP_N = 50                    # Größe der Ergebnisliste
ACTIVE_WITHIN_DAYS = 7        # Aktivitätsfenster vor dem Stichtag (00:00 UTC)
SEARCH_LIMIT = 100            # limit-Parameter von contacts.search; Server deckelt selbst

# ----------------------------------------------------------------------------------------------------
# Betriebsparameter (kein Einfluss auf das Kriterium)
# ----------------------------------------------------------------------------------------------------
TELETHON_PIN = "1.45.0"       # PyPI-Release vom 2026-09-10 (direkt geprüft am 2026-09-29)
FLOOD_WAIT_MAX_SECONDS = 300  # längere FloodWaits -> Abbruch ohne kanonische Ausgabe
DEFAULT_SLEEP_SECONDS = 1.5   # Pause zwischen API-Aufrufen
HISTORY_PEEK = 5              # Nachrichten, die je Kanal auf einen regulären Post geprüft werden
ABOUT_SNIPPET_CHARS = 120

ENV_API_ID = "TG_API_ID"
ENV_API_HASH = "TG_API_HASH"
ENV_SESSION = "TG_SESSION"
DEFAULT_SESSION_PATH = ".secrets/edge_lab.session"

CSV_COLUMNS = [
    "rank",
    "channel_id",
    "username",
    "title",
    "participants_count",
    "last_post_utc",
    "matched_keywords",
    "verified",
    "scam",
    "fake",
    "restricted",
    "retrieved_at_utc",
    "criterion_version",
]
RAW_CSV_COLUMNS = CSV_COLUMNS + ["included", "exclusion_reason", "error", "about_snippet"]


class ConfigError(Exception):
    """Ungültige Konfiguration (Exit 1)."""


class RunAborted(Exception):
    """Lauf abgebrochen; keine kanonische Ausgabe (Exit 3)."""


@dataclasses.dataclass(frozen=True)
class Config:
    date: dt.date                    # Stichtag (UTC)
    out_dir: Path
    keywords: tuple[str, ...]
    top_n: int
    active_within_days: int
    search_limit: int
    sleep_seconds: float
    with_global_search: bool         # optionaler Zusatzschritt (macht den Lauf "custom")
    dry_run: bool
    session_path: Path
    criterion_version: str

    @property
    def activity_cutoff(self) -> dt.datetime:
        """Beginn des Aktivitätsfensters: Stichtag 00:00 UTC minus active_within_days."""
        start = dt.datetime.combine(self.date, dt.time(0, 0), tzinfo=dt.timezone.utc)
        return start - dt.timedelta(days=self.active_within_days)

    @property
    def date_tag(self) -> str:
        return self.date.isoformat()

    def path_top(self) -> Path:
        return self.out_dir / f"channels_{self.date_tag}.csv"

    def path_raw(self) -> Path:
        return self.out_dir / f"channels_{self.date_tag}_raw.csv"

    def path_meta(self) -> Path:
        return self.out_dir / f"channels_{self.date_tag}.meta.json"


# ----------------------------------------------------------------------------------------------------
# Reine Hilfsfunktionen (stdlib, testbar ohne Netz)
# ----------------------------------------------------------------------------------------------------
def utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def iso_utc(value: Optional[dt.datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def criterion_hash(keywords: tuple[str, ...], top_n: int, active_within_days: int,
                   search_limit: int, with_global_search: bool) -> str:
    payload = {
        "keywords": list(keywords),
        "top_n": top_n,
        "active_within_days": active_within_days,
        "search_limit": search_limit,
        "with_global_search": with_global_search,
    }
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def keywords_hash(keywords: tuple[str, ...]) -> str:
    """SHA-256 nur über die Keyword-Liste (kanonisches JSON-Array)."""
    return sha256_bytes(canonical_json(list(keywords)).encode("utf-8"))


def load_keywords(path: Optional[Path]) -> tuple[str, ...]:
    """Liest eine Keyword-Datei (eine Zeile je Keyword, '#' = Kommentar) oder liefert KEYWORDS."""
    if path is None:
        return KEYWORDS
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return tuple(lines)


def validate_keywords(keywords: tuple[str, ...]) -> None:
    if not keywords:
        raise ConfigError("Keyword-Liste ist leer.")
    lowered = [k.lower() for k in keywords]
    if len(set(lowered)) != len(lowered):
        raise ConfigError("Keyword-Liste enthält Duplikate (case-insensitiv).")
    for k in keywords:
        if k != k.strip() or "\n" in k or "\t" in k:
            raise ConfigError(f"Ungültiges Keyword: {k!r}")


def parse_date(value: Optional[str]) -> dt.date:
    if value is None:
        return utc_now().date()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"--date muss ISO-8601 (YYYY-MM-DD) sein, nicht {value!r}") from exc


def build_config(args: argparse.Namespace) -> Config:
    keywords = load_keywords(Path(args.keywords_file) if args.keywords_file else None)
    validate_keywords(keywords)
    if args.top <= 0:
        raise ConfigError("--top muss > 0 sein.")
    if args.sleep < 0:
        raise ConfigError("--sleep muss >= 0 sein.")

    is_custom = (
        keywords != KEYWORDS
        or args.top != TOP_N
        or bool(args.with_global_search)
    )
    if is_custom:
        digest = criterion_hash(keywords, args.top, ACTIVE_WITHIN_DAYS, SEARCH_LIMIT,
                                bool(args.with_global_search))
        criterion_version = f"{CRITERION_VERSION}-custom-{digest[:8]}"
    else:
        criterion_version = CRITERION_VERSION

    session_env = os.environ.get(ENV_SESSION)
    return Config(
        date=parse_date(args.date),
        out_dir=Path(args.out_dir),
        keywords=keywords,
        top_n=args.top,
        active_within_days=ACTIVE_WITHIN_DAYS,
        search_limit=SEARCH_LIMIT,
        sleep_seconds=args.sleep,
        with_global_search=bool(args.with_global_search),
        dry_run=bool(args.dry_run),
        session_path=Path(session_env) if session_env else Path(DEFAULT_SESSION_PATH),
        criterion_version=criterion_version,
    )


def sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
    """participants_count absteigend, None ans Ende, Tiebreak channel_id aufsteigend."""
    pc = row.get("participants_count")
    missing = 1 if pc in (None, "") else 0
    return (missing, -(int(pc) if not missing else 0), int(row["channel_id"]))


def rank_rows(rows: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    included = [r for r in rows if r.get("included")]
    included.sort(key=sort_key)
    ranked = []
    for i, row in enumerate(included[:top_n], start=1):
        out = {col: row.get(col, "") for col in CSV_COLUMNS}
        out["rank"] = i
        ranked.append(out)
    return ranked


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, quoting=csv.QUOTE_ALL,
                                lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: ("" if row.get(col) is None else row.get(col)) for col in columns})


def write_meta(path: Path, meta: dict[str, Any]) -> None:
    path.write_text(json.dumps(meta, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def request_budget(cfg: Config, n_candidates: Optional[int] = None) -> dict[str, Any]:
    """Grobe Obergrenze der API-Aufrufe ohne FloodWait-Wiederholungen (Worst Case ×2): 1 Suche je Keyword
    (+1 bei globaler Suche), 2 je Kandidat; Kandidaten-Obergrenze = Suchen × SEARCH_LIMIT."""
    per_keyword = 2 if cfg.with_global_search else 1
    searches = len(cfg.keywords) * per_keyword
    if n_candidates is None:
        n_candidates = searches * cfg.search_limit  # Obergrenze
    return {
        "search_calls": searches,
        "candidates_upper_bound": n_candidates,
        "per_candidate_calls": 2,
        "total_upper_bound": searches + 2 * n_candidates,
        "estimated_seconds_at_sleep": round((searches + 2 * n_candidates) * cfg.sleep_seconds),
    }


def env_status() -> dict[str, bool]:
    """Nur Vorhandensein melden – niemals Werte ausgeben."""
    return {
        ENV_API_ID: bool(os.environ.get(ENV_API_ID)),
        ENV_API_HASH: bool(os.environ.get(ENV_API_HASH)),
        ENV_SESSION: bool(os.environ.get(ENV_SESSION)),
    }


def telethon_available() -> bool:
    try:
        return importlib.util.find_spec("telethon") is not None
    except ValueError:  # Modul bereits importiert, aber ohne __spec__ (z. B. in Tests)
        return "telethon" in sys.modules


def dry_run_report(cfg: Config) -> dict[str, Any]:
    return {
        "mode": "dry-run (kein Netz, keine Ausgabe geschrieben)",
        "criterion_version": cfg.criterion_version,
        "freeze_capable": cfg.criterion_version == CRITERION_VERSION,
        "date": cfg.date_tag,
        "activity_cutoff_utc": iso_utc(cfg.activity_cutoff),
        "keywords": list(cfg.keywords),
        "keywords_sha256": keywords_hash(cfg.keywords),
        "criterion_sha256": criterion_hash(cfg.keywords, cfg.top_n, cfg.active_within_days,
                                           cfg.search_limit, cfg.with_global_search),
        "top_n": cfg.top_n,
        "active_within_days": cfg.active_within_days,
        "search_limit": cfg.search_limit,
        "with_global_search": cfg.with_global_search,
        "planned_outputs": [str(cfg.path_top()), str(cfg.path_raw()), str(cfg.path_meta())],
        "request_budget": request_budget(cfg),
        "env_present": env_status(),
        "session_path": str(cfg.session_path),
        "telethon_importable": telethon_available(),
        "telethon_pin": TELETHON_PIN,
        "python": platform.python_version(),
    }


# ----------------------------------------------------------------------------------------------------
# Telegram-Lauf (Telethon wird erst hier importiert)
# ----------------------------------------------------------------------------------------------------
async def run(cfg: Config) -> int:
    try:
        import telethon  # type: ignore
        from telethon import TelegramClient, errors, functions, types  # type: ignore
        from telethon.tl.alltlobjects import LAYER  # type: ignore
    except ImportError:
        print(f"Telethon fehlt. Installieren mit: pip install telethon=={TELETHON_PIN}", file=sys.stderr)
        return 2

    api_id_raw = os.environ.get(ENV_API_ID)
    api_hash = os.environ.get(ENV_API_HASH)
    if not api_id_raw or not api_hash:
        print(f"Fehlende Umgebungsvariablen {ENV_API_ID}/{ENV_API_HASH} (siehe README).", file=sys.stderr)
        return 2
    try:
        api_id = int(api_id_raw)
    except ValueError:
        print(f"{ENV_API_ID} muss eine Zahl sein.", file=sys.stderr)
        return 2

    cfg.session_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(cfg.session_path.parent, 0o700)
    except OSError:
        pass

    log: list[str] = []
    counters: dict[str, int] = {
        "search_calls": 0, "full_channel_calls": 0, "history_calls": 0,
        "found_total": 0, "found_broadcast": 0, "after_dedupe": 0,
        "active": 0, "inactive": 0, "activity_unknown": 0, "errors": 0,
        "participants_count_missing": 0, "flood_waits": 0, "keywords_skipped": 0,
    }
    per_keyword_hits: dict[str, int] = {}
    errors_list: list[dict[str, str]] = []

    async def guarded(label: str, factory):
        """Führt einen API-Aufruf aus; FloodWait <= Max wird abgewartet und einmal wiederholt."""
        for attempt in (1, 2):
            try:
                result = await factory()
                await asyncio.sleep(cfg.sleep_seconds)
                return result
            except errors.FloodWaitError as exc:
                counters["flood_waits"] += 1
                if exc.seconds > FLOOD_WAIT_MAX_SECONDS or attempt == 2:
                    raise RunAborted(f"FloodWait {exc.seconds}s bei {label} – Abbruch") from exc
                log.append(f"FloodWait {exc.seconds}s bei {label}; warte und wiederhole einmal")
                await asyncio.sleep(exc.seconds + 1)
        raise RunAborted(f"unerreichbar: {label}")

    client = TelegramClient(str(cfg.session_path), api_id, api_hash)
    client.flood_sleep_threshold = 0  # FloodWaits selbst behandeln (guarded)

    retrieved_at = utc_now()
    candidates: dict[int, dict[str, Any]] = {}       # channel_id -> Zeile
    entities: dict[int, Any] = {}                     # channel_id -> Channel-Objekt aus der Suche

    async with client:
        try:
            os.chmod(cfg.session_path, 0o600)
        except OSError:
            pass

        # 1) Suche je Keyword (contacts.search) – Reihenfolge = KEYWORDS
        for kw in cfg.keywords:
            try:
                res = await guarded(f"contacts.search({kw!r})",
                                    lambda kw=kw: client(functions.contacts.SearchRequest(q=kw, limit=cfg.search_limit)))
            except errors.RPCError as exc:  # z. B. QUERY_TOO_SHORT, SEARCH_QUERY_EMPTY
                counters["keywords_skipped"] += 1
                errors_list.append({"stage": "search", "keyword": kw, "error": type(exc).__name__})
                log.append(f"Keyword übersprungen ({type(exc).__name__}): {kw!r}")
                continue
            counters["search_calls"] += 1
            chats = list(getattr(res, "chats", []) or [])
            if cfg.with_global_search:
                gres = await guarded(f"messages.searchGlobal({kw!r})", lambda kw=kw: client(
                    functions.messages.SearchGlobalRequest(
                        q=kw, filter=types.InputMessagesFilterEmpty(), min_date=None, max_date=None,
                        offset_rate=0, offset_peer=types.InputPeerEmpty(), offset_id=0,
                        limit=cfg.search_limit, broadcasts_only=True)))
                counters["search_calls"] += 1
                chats.extend(getattr(gres, "chats", []) or [])
            hits = 0
            for chat in chats:
                counters["found_total"] += 1
                if not isinstance(chat, types.Channel):
                    continue
                if not chat.broadcast or chat.megagroup:
                    continue
                counters["found_broadcast"] += 1
                hits += 1
                row = candidates.get(chat.id)
                if row is None:
                    row = {
                        "channel_id": chat.id,
                        "username": "",
                        "title": chat.title or "",
                        "participants_count": None,
                        "last_post_utc": "",
                        "matched_keywords": [],
                        "verified": "", "scam": "", "fake": "", "restricted": "",
                        "retrieved_at_utc": iso_utc(retrieved_at),
                        "criterion_version": cfg.criterion_version,
                        "included": False, "exclusion_reason": "", "error": "", "about_snippet": "",
                    }
                    candidates[chat.id] = row
                    entities[chat.id] = chat
                if kw not in row["matched_keywords"]:
                    row["matched_keywords"].append(kw)
            per_keyword_hits[kw] = hits
        counters["after_dedupe"] = len(candidates)

        # 2) Anreicherung je Kanal: getFullChannel + letzter regulärer Post
        for cid in sorted(candidates):
            row = candidates[cid]
            ent = entities[cid]
            try:
                full = await guarded(f"channels.getFullChannel({cid})",
                                     lambda ent=ent: client(functions.channels.GetFullChannelRequest(channel=ent)))
                counters["full_channel_calls"] += 1
                full_chat = full.full_chat
                chat_obj = next((c for c in full.chats if getattr(c, "id", None) == cid), ent)
                pc = getattr(full_chat, "participants_count", None)
                row["participants_count"] = pc
                if pc is None:
                    counters["participants_count_missing"] += 1
                about = getattr(full_chat, "about", "") or ""
                row["about_snippet"] = about.replace("\n", " ")[:ABOUT_SNIPPET_CHARS]
                row["title"] = getattr(chat_obj, "title", row["title"]) or row["title"]
                username = getattr(chat_obj, "username", None)
                if not username:
                    for u in (getattr(chat_obj, "usernames", None) or []):
                        if getattr(u, "active", False) and getattr(u, "username", None):
                            username = u.username
                            break
                row["username"] = username or ""
                for flag in ("verified", "scam", "fake", "restricted"):
                    row[flag] = bool(getattr(chat_obj, flag, False))

                last_post: Optional[dt.datetime] = None
                async def _history(ent=ent):
                    msgs = []
                    async for m in client.iter_messages(ent, limit=HISTORY_PEEK):
                        msgs.append(m)
                    return msgs
                msgs = await guarded(f"messages.getHistory({cid})", _history)
                counters["history_calls"] += 1
                for m in msgs:
                    if isinstance(m, types.MessageService):
                        continue
                    if getattr(m, "date", None) is not None:
                        last_post = m.date
                        break
                if last_post is None:
                    counters["activity_unknown"] += 1
                    row["exclusion_reason"] = "activity_unknown"
                    continue
                row["last_post_utc"] = iso_utc(last_post)
                if last_post.astimezone(dt.timezone.utc) >= cfg.activity_cutoff:
                    row["included"] = True
                    counters["active"] += 1
                else:
                    row["exclusion_reason"] = "inactive"
                    counters["inactive"] += 1
            except RunAborted:
                raise
            except errors.RPCError as exc:  # ChannelPrivateError u. a.
                counters["errors"] += 1
                row["error"] = type(exc).__name__
                row["exclusion_reason"] = "error"
                errors_list.append({"stage": "enrich", "channel_id": str(cid), "error": type(exc).__name__})

    # 3) Ranking und Ausgabe (nur bei vollständigem Lauf)
    rows = list(candidates.values())
    for r in rows:
        r["matched_keywords"] = ";".join(r["matched_keywords"])
    ranked = rank_rows(rows, cfg.top_n)
    raw_rows = sorted(rows, key=sort_key)

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(cfg.path_top(), ranked, CSV_COLUMNS)
    write_csv(cfg.path_raw(), raw_rows, RAW_CSV_COLUMNS)

    meta = {
        "criterion_version": cfg.criterion_version,
        "freeze_capable": cfg.criterion_version == CRITERION_VERSION,
        "date": cfg.date_tag,
        "activity_cutoff_utc": iso_utc(cfg.activity_cutoff),
        "retrieved_at_utc": iso_utc(retrieved_at),
        "finished_at_utc": iso_utc(utc_now()),
        "keywords": list(cfg.keywords),
        "keywords_sha256": keywords_hash(cfg.keywords),
        "criterion_sha256": criterion_hash(cfg.keywords, cfg.top_n, cfg.active_within_days,
                                           cfg.search_limit, cfg.with_global_search),
        "per_keyword_broadcast_hits": per_keyword_hits,
        "top_n": cfg.top_n,
        "active_within_days": cfg.active_within_days,
        "search_limit": cfg.search_limit,
        "with_global_search": cfg.with_global_search,
        "sleep_seconds": cfg.sleep_seconds,
        "counters": counters,
        "errors": errors_list,
        "log": log,
        "outputs": {
            "top_csv": {"path": str(cfg.path_top()), "sha256": sha256_file(cfg.path_top()),
                        "rows": len(ranked)},
            "raw_csv": {"path": str(cfg.path_raw()), "sha256": sha256_file(cfg.path_raw()),
                        "rows": len(raw_rows)},
        },
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "telethon_version": getattr(telethon, "__version__", "unknown"),
        "telethon_layer": LAYER,
        "python": platform.python_version(),
    }
    write_meta(cfg.path_meta(), meta)
    print(json.dumps({"written": [str(cfg.path_top()), str(cfg.path_raw()), str(cfg.path_meta())],
                      "top_rows": len(ranked), "candidates": len(raw_rows),
                      "criterion_version": cfg.criterion_version}, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------------------------------
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Edge Lab EXP001 Anhang A – Telegram-Kanal-Discovery (Kriterium A.1)")
    p.add_argument("--date", help="Stichtag YYYY-MM-DD (UTC); Default: heute (UTC)")
    p.add_argument("--out-dir", default="data", help="Ausgabeverzeichnis (Default: data)")
    p.add_argument("--top", type=int, default=TOP_N, help=f"Anzahl Kanäle (Default {TOP_N}; Abweichung = custom, nicht freeze-fähig)")
    p.add_argument("--keywords-file", help="Keyword-Datei statt fester Liste (custom, nicht freeze-fähig)")
    p.add_argument("--with-global-search", action="store_true",
                   help="zusätzlich messages.searchGlobal(broadcasts_only) je Keyword (custom, nicht freeze-fähig)")
    p.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS, help="Pause zwischen API-Aufrufen in Sekunden")
    p.add_argument("--dry-run", action="store_true", help="nur Konfiguration prüfen: kein Netz, kein Import, keine Ausgabe")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        cfg = build_config(args)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 1
    if cfg.dry_run:
        print(json.dumps(dry_run_report(cfg), ensure_ascii=False, indent=2))
        return 0
    if not telethon_available():
        print(f"Telethon fehlt. Installieren mit: pip install telethon=={TELETHON_PIN}", file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(cfg))
    except RunAborted as exc:
        print(f"Abbruch: {exc}. Keine kanonischen Ausgabedateien geschrieben.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
