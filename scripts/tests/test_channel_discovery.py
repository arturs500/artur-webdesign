"""
Tests für scripts/channel_discovery.py – ohne Netz, ohne Telethon-Installation.

Ein Fake-`telethon`-Paket wird in sys.modules registriert; der Fake-Client spielt Suchergebnisse,
getFullChannel-Antworten, Nachrichtenhistorien und Fehler (FloodWait, ChannelPrivate) ab.
Ausführen: python3 -m unittest scripts/tests/test_channel_discovery.py
"""
from __future__ import annotations

import asyncio
import contextlib
import csv
import datetime as dt
import hashlib
import importlib.machinery
import io
import json
import os
import sys
import tempfile
import types as pytypes
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import channel_discovery as cd  # noqa: E402

UTC = dt.timezone.utc


# ----------------------------------------------------------------------------------------------------
# Fake-Telethon
# ----------------------------------------------------------------------------------------------------
class RPCError(Exception):
    pass


class FloodWaitError(RPCError):
    def __init__(self, seconds: int):
        super().__init__(f"FloodWait {seconds}")
        self.seconds = seconds


class ChannelPrivateError(RPCError):
    pass


class QueryTooShortError(RPCError):
    pass


class SearchRequest:
    def __init__(self, q, limit):
        self.q, self.limit = q, limit


class GetFullChannelRequest:
    def __init__(self, channel):
        self.channel = channel


class SearchGlobalRequest:
    def __init__(self, **kw):
        self.kw = kw


class Channel:
    def __init__(self, id, title, broadcast=True, megagroup=False, username=None, usernames=None,
                 verified=False, scam=False, fake=False, restricted=False, min=False):
        self.id, self.title = id, title
        self.broadcast, self.megagroup = broadcast, megagroup
        self.username, self.usernames = username, usernames or []
        self.verified, self.scam, self.fake, self.restricted, self.min = verified, scam, fake, restricted, min


class Username:
    def __init__(self, username, active=True):
        self.username, self.active = username, active


class ChannelFull:
    def __init__(self, participants_count=None, about=""):
        self.participants_count, self.about = participants_count, about


class Message:
    def __init__(self, date):
        self.date = date


class MessageService:
    def __init__(self, date):
        self.date = date


class User:
    pass


def install_fake_telethon(client_cls):
    tele = pytypes.ModuleType("telethon")
    tele.__version__ = "0.0-fake"
    tele.__spec__ = importlib.machinery.ModuleSpec("telethon", None)  # find_spec() braucht ein spec
    errors = pytypes.ModuleType("telethon.errors")
    errors.RPCError, errors.FloodWaitError = RPCError, FloodWaitError
    errors.ChannelPrivateError, errors.QueryTooShortError = ChannelPrivateError, QueryTooShortError
    functions = pytypes.ModuleType("telethon.functions")
    functions.contacts = SimpleNamespace(SearchRequest=SearchRequest)
    functions.channels = SimpleNamespace(GetFullChannelRequest=GetFullChannelRequest)
    functions.messages = SimpleNamespace(SearchGlobalRequest=SearchGlobalRequest)
    types_mod = pytypes.ModuleType("telethon.types")
    types_mod.Channel, types_mod.ChannelFull, types_mod.Username = Channel, ChannelFull, Username
    types_mod.Message, types_mod.MessageService, types_mod.User = Message, MessageService, User
    types_mod.InputMessagesFilterEmpty = lambda: None
    types_mod.InputPeerEmpty = lambda: None
    tl = pytypes.ModuleType("telethon.tl")
    alltl = pytypes.ModuleType("telethon.tl.alltlobjects")
    alltl.LAYER = 0
    tl.alltlobjects = alltl
    tele.TelegramClient, tele.errors, tele.functions, tele.types, tele.tl = client_cls, errors, functions, types_mod, tl
    for name, mod in {"telethon": tele, "telethon.errors": errors, "telethon.functions": functions,
                      "telethon.types": types_mod, "telethon.tl": tl, "telethon.tl.alltlobjects": alltl}.items():
        sys.modules[name] = mod


def uninstall_fake_telethon():
    for name in list(sys.modules):
        if name == "telethon" or name.startswith("telethon."):
            del sys.modules[name]


NOW = dt.datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
FRESH = dt.datetime(2026, 10, 14, 9, 0, tzinfo=UTC)      # innerhalb 7 Tage vor Stichtag 2026-10-15
STALE = dt.datetime(2026, 9, 1, 9, 0, tzinfo=UTC)        # älter als Cutoff 2026-10-08


def make_world():
    """Kanäle: A/G gleiche Abonnenten (Tiebreak id), B ohne participants_count, C Megagroup,
    D nur Service-Nachricht, E privat (Fehler), F inaktiv."""
    A = Channel(200, "Alpha Calls", username="alpha")
    G = Channel(100, "Gamma Gems", username=None, usernames=[Username("gamma_old", active=False), Username("gamma", True)])
    B = Channel(300, "Beta Ohne Zahl", username="beta", scam=True)
    C = Channel(400, "Chat Gruppe", megagroup=True, username="chatgrp")
    D = Channel(500, "Delta Service", username="delta")
    E = Channel(600, "Epsilon Privat", username="eps")
    F = Channel(700, "Foxtrot Alt", username="fox")
    search = {
        "solana": [A, B, C, D, User()],
        "pump.fun": [A, G, E, F],
    }
    full = {
        200: ChannelFull(1000, "Alpha about\nzweite Zeile"),
        100: ChannelFull(1000, "Gamma about"),
        300: ChannelFull(None, "Beta about"),
        500: ChannelFull(50, ""),
        600: ChannelPrivateError(),
        700: ChannelFull(5000, "old"),
    }
    history = {
        200: [Message(FRESH)],
        100: [MessageService(FRESH), Message(FRESH - dt.timedelta(hours=1))],
        300: [Message(FRESH)],
        500: [MessageService(FRESH)],
        700: [Message(STALE)],
    }
    return search, full, history


class FakeClientFactory:
    """Erzeugt eine TelegramClient-Ersatzklasse mit skriptbaren Antworten."""

    def __init__(self, search, full, history, flood_first=None):
        self.search, self.full, self.history = search, full, history
        self.flood_first = dict(flood_first or {})   # channel_id -> seconds beim ersten GetFullChannel
        self.calls = []
        factory = self

        class FakeClient:
            def __init__(self, session, api_id, api_hash):
                self.session, self.api_id, self.api_hash = session, api_id, api_hash
                self.flood_sleep_threshold = 60
                Path(session).write_bytes(b"")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def __call__(self, request):
                factory.calls.append(request)
                if isinstance(request, SearchRequest):
                    return SimpleNamespace(chats=list(factory.search.get(request.q, [])), users=[])
                if isinstance(request, GetFullChannelRequest):
                    cid = request.channel.id
                    if cid in factory.flood_first:
                        secs = factory.flood_first.pop(cid)
                        raise FloodWaitError(secs)
                    res = factory.full[cid]
                    if isinstance(res, Exception):
                        raise res
                    return SimpleNamespace(full_chat=res, chats=[request.channel], users=[])
                raise AssertionError(f"unerwarteter Request {request!r}")

            async def iter_messages(self, entity, limit):
                for m in factory.history.get(entity.id, [])[:limit]:
                    yield m

        self.cls = FakeClient


class ChannelDiscoveryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "data"
        self.env = {"TG_API_ID": "12345", "TG_API_HASH": "x" * 32,
                    "TG_SESSION": str(Path(self.tmp.name) / ".secrets" / "t.session")}
        self._old_env = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.sleeps = []
        self._orig_sleep = cd.asyncio.sleep

        async def fake_sleep(s):
            self.sleeps.append(s)
        cd.asyncio.sleep = fake_sleep

    def tearDown(self):
        cd.asyncio.sleep = self._orig_sleep
        uninstall_fake_telethon()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def config(self, **over):
        args = cd.parse_args(["--date", "2026-10-15", "--out-dir", str(self.out), "--sleep", "0"])
        cfg = cd.build_config(args)
        return cd.dataclasses.replace(cfg, keywords=("solana", "pump.fun"), criterion_version="TEST", **over)

    def test_full_run_writes_ranked_outputs(self):
        search, full, history = make_world()
        factory = FakeClientFactory(search, full, history, flood_first={200: 5})
        install_fake_telethon(factory.cls)
        cfg = self.config()
        with contextlib.redirect_stdout(io.StringIO()):
            rc = asyncio.run(cd.run(cfg))
        self.assertEqual(rc, 0)

        with cfg.path_top().open(encoding="utf-8", newline="") as fh:
            top = list(csv.DictReader(fh))
        self.assertEqual([r["channel_id"] for r in top], ["100", "200", "300"])   # 1000/1000 Tiebreak id, None zuletzt
        self.assertEqual([r["rank"] for r in top], ["1", "2", "3"])
        self.assertEqual(top[0]["username"], "gamma")                              # aktiver Sammel-Username
        self.assertEqual(top[1]["matched_keywords"], "solana;pump.fun")
        self.assertEqual(top[2]["participants_count"], "")
        self.assertEqual(top[2]["scam"], "True")
        self.assertEqual(top[0]["last_post_utc"], "2026-10-14T08:00:00Z")          # Service-Nachricht übersprungen
        self.assertEqual(set(top[0].keys()), set(cd.CSV_COLUMNS))

        with cfg.path_raw().open(encoding="utf-8", newline="") as fh:
            raw = list(csv.DictReader(fh))
        by_id = {r["channel_id"]: r for r in raw}
        self.assertEqual(len(raw), 6)                                              # Megagroup und User nie aufgenommen
        self.assertEqual(by_id["500"]["exclusion_reason"], "activity_unknown")
        self.assertEqual(by_id["600"]["exclusion_reason"], "error")
        self.assertEqual(by_id["600"]["error"], "ChannelPrivateError")
        self.assertEqual(by_id["700"]["exclusion_reason"], "inactive")
        self.assertEqual(by_id["200"]["about_snippet"], "Alpha about zweite Zeile")

        meta = json.loads(cfg.path_meta().read_text(encoding="utf-8"))
        c = meta["counters"]
        self.assertEqual((c["after_dedupe"], c["active"], c["inactive"], c["activity_unknown"], c["errors"]),
                         (6, 3, 1, 1, 1))
        self.assertEqual(c["participants_count_missing"], 1)
        self.assertEqual(c["flood_waits"], 1)
        self.assertIn(6, self.sleeps)                                              # FloodWait 5 s + 1 abgewartet
        self.assertEqual(meta["outputs"]["top_csv"]["sha256"],
                         hashlib.sha256(cfg.path_top().read_bytes()).hexdigest())
        self.assertEqual(meta["script_sha256"], hashlib.sha256(Path(cd.__file__).read_bytes()).hexdigest())
        self.assertEqual(meta["per_keyword_broadcast_hits"], {"solana": 3, "pump.fun": 4})
        self.assertFalse(meta["freeze_capable"])                                   # criterion_version TEST

    def test_long_floodwait_aborts_without_outputs(self):
        search, full, history = make_world()
        factory = FakeClientFactory(search, full, history, flood_first={200: 999})
        install_fake_telethon(factory.cls)
        cfg = self.config()
        with self.assertRaises(cd.RunAborted):
            asyncio.run(cd.run(cfg))
        self.assertFalse(self.out.exists())

    def test_main_returns_3_on_abort(self):
        search, full, history = make_world()
        factory = FakeClientFactory(search, full, history, flood_first={200: 999})
        install_fake_telethon(factory.cls)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cd.main(["--date", "2026-10-15", "--out-dir", str(self.out), "--sleep", "0"])
        self.assertEqual(rc, 3)
        self.assertFalse(self.out.exists())

    def test_search_error_skips_keyword(self):
        search, full, history = make_world()
        factory = FakeClientFactory(search, full, history)
        orig_call = factory.cls.__call__

        async def call(self_, request):
            if isinstance(request, SearchRequest) and request.q == "solana":
                raise QueryTooShortError()
            return await orig_call(self_, request)
        factory.cls.__call__ = call
        install_fake_telethon(factory.cls)
        cfg = self.config()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(asyncio.run(cd.run(cfg)), 0)
        meta = json.loads(cfg.path_meta().read_text(encoding="utf-8"))
        self.assertEqual(meta["counters"]["keywords_skipped"], 1)
        self.assertEqual(meta["counters"]["after_dedupe"], 4)                     # nur pump.fun-Treffer


class PureFunctionTests(unittest.TestCase):
    def test_dry_run_writes_nothing_and_is_freeze_capable(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "data"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cd.main(["--dry-run", "--out-dir", str(out), "--date", "2026-10-15"])
            self.assertEqual(rc, 0)
            report = json.loads(buf.getvalue())
            self.assertTrue(report["freeze_capable"])
            self.assertIn("criterion_sha256", report)
            self.assertEqual(report["keywords_sha256"], cd.keywords_hash(cd.KEYWORDS))
            self.assertFalse(out.exists())
            cfg = cd.build_config(cd.parse_args(["--dry-run", "--date", "2026-10-15"]))
            self.assertEqual(cfg.criterion_version, cd.CRITERION_VERSION)
            self.assertEqual(cfg.activity_cutoff, dt.datetime(2026, 10, 8, 0, 0, tzinfo=UTC))

    def test_custom_parameters_mark_run_as_not_freeze_capable(self):
        cfg = cd.build_config(cd.parse_args(["--top", "10"]))
        self.assertTrue(cfg.criterion_version.startswith("A.1-custom-"))
        cfg2 = cd.build_config(cd.parse_args(["--with-global-search"]))
        self.assertTrue(cfg2.criterion_version.startswith("A.1-custom-"))
        self.assertNotEqual(cfg.criterion_version, cfg2.criterion_version)

    def test_keywords_validation(self):
        with self.assertRaises(cd.ConfigError):
            cd.validate_keywords(())
        with self.assertRaises(cd.ConfigError):
            cd.validate_keywords(("Solana", "solana"))
        with self.assertRaises(cd.ConfigError):
            cd.validate_keywords((" solana",))
        cd.validate_keywords(cd.KEYWORDS)

    def test_bad_date_is_config_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cd.main(["--dry-run", "--date", "15.10.2026"]), 1)

    def test_sort_key_and_rank(self):
        rows = [
            {"channel_id": 3, "participants_count": 100, "included": True},
            {"channel_id": 1, "participants_count": None, "included": True},
            {"channel_id": 2, "participants_count": 100, "included": True},
            {"channel_id": 4, "participants_count": 500, "included": False},
            {"channel_id": 5, "participants_count": 7, "included": True},
        ]
        ranked = cd.rank_rows(rows, 3)
        self.assertEqual([r["channel_id"] for r in ranked], [2, 3, 5])
        self.assertEqual([r["rank"] for r in ranked], [1, 2, 3])

    def test_request_budget(self):
        cfg = cd.build_config(cd.parse_args([]))
        b = cd.request_budget(cfg)
        self.assertEqual(b["search_calls"], len(cd.KEYWORDS))
        self.assertEqual(b["total_upper_bound"], len(cd.KEYWORDS) + 2 * len(cd.KEYWORDS) * cd.SEARCH_LIMIT)


if __name__ == "__main__":
    unittest.main()
