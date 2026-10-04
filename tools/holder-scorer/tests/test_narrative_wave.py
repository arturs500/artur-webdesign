"""Narrativ-Welle (0.3.3, OQ-028): Begriffe, Themen-Register, Zeile `Them` in der Nachricht, Quelle aus Metadaten,
Beobachtungsliste (--beobachte) und die Latenz-Zeile im tape report."""
from __future__ import annotations

from holder_scorer.calibrate import alert_record_extra
from holder_scorer.cli import build_parser
from holder_scorer.encoding import b58encode
from holder_scorer.live import Alert
from holder_scorer.narrative import ThemeRegistry, link_anchors, terms, theme_line
from holder_scorer.notify import format_short
from holder_scorer.replay import evaluate, format_report, latency_stats
from tests.helpers import key
from tests.test_live import T0, feed_buyers, launch_msg, make_engine


def test_terms_and_link_anchors_normalize():
    assert terms("TrumpCoin 2024", "$TRUMP") == {"trump"}  # "coin" ist Füllwort, Zahlen fallen weg, CamelCase wird getrennt
    assert terms("Elon just posted about tiffany lamps") == {"elon", "posted", "about", "tiffany", "lamps"}
    assert terms("test", "aaa", "", None) == set()
    assert link_anchors({"twitter": "https://x.com/elonmusk/status/123?s=20", "telegram": "https://t.me/", "website": "www.Tiffany-Lamps.io/"}) == {"x.com/elonmusk/status/123", "tiffany-lamps.io"}
    assert link_anchors({"twitter": "https://twitter.com/elonmusk/status/123"}) == {"x.com/elonmusk/status/123"}
    assert link_anchors({"website": "https://pump.fun/coin/abc", "twitter": "x.com"}) == set()
    assert link_anchors(None) == set()


def test_theme_registry_wave_needs_many_devs_and_a_rate_above_baseline():
    reg = ThemeRegistry()
    t = 1_800_000_000.0
    for i in range(30):  # Grundrate: ein "pepe" alle 10 Minuten über 5 Stunden
        reg.register(f"P{i}", f"C{i}", ["Pepe Classic", "PEPE"], t + i * 600)
    now = t + 30 * 600 + 60
    for i in range(4):
        reg.register(f"N{i}", f"D{i}", ["Pepe Returns"], now - 300 + i * 60)
    s = reg.stats("pepe", now, "N0")
    assert s is not None and s.n_recent == 4 and s.devs_recent == 4 and 1.0 <= s.baseline <= 1.1 and not s.wave  # 4 ≈ 3,9 × Grundrate
    reg.register("N4", "D4", ["Pepe Again"], now - 30)
    s = reg.stats("pepe", now, "N4")
    assert s.n_recent == 5 and s.wave and s.position == 5 and s.mints[0] == "N0"
    # ein neuer Begriff: vier Launches von vier Devs reichen (Mindestgrundrate 0,5)
    for i in range(4):
        reg.register(f"T{i}", f"E{i}", ["Tiffany Blue", "TIFF"], now - 120 + i * 30)
    s = reg.stats("tiffany", now, "T0")
    assert s.wave and s.baseline == 0 and s.ratio == 8.0 and s.position == 1
    # derselbe Dev viermal: keine Welle
    for i in range(4):
        reg.register(f"S{i}", "SAME", ["Serial Bot"], now - 100 + i * 20)
    assert not reg.stats("serial", now).wave and reg.stats("serial", now).devs_recent == 1
    best = reg.theme_for("T3", now)
    assert best is not None and best.term in ("tiffany", "blue", "tiff") and best.wave
    assert reg.theme_for("unbekannt", now) is None
    # Historie: nach sechs Stunden ist der Begriff vergessen; aufgeräumt wird beim nächsten Registrieren
    assert reg.stats("tiffany", now + 7 * 3600) is None
    reg.register("X", "Y", ["Fresh Start"], now + 7 * 3600)
    assert reg.terms_of("T0") == set() and reg.stats("pepe", now + 7 * 3600) is None


def _launch(engine, mint, creator, name, symbol, now):
    msg = launch_msg(mint, creator)
    msg["name"], msg["symbol"] = name, symbol
    return engine.on_launch(msg, now=now)


def test_live_theme_line_rank_by_inflow_and_record_field():
    engine, alerts = make_engine(stufe=2)
    mints, creators = [key() for _ in range(4)], [key() for _ in range(4)]
    for i, (m, c) in enumerate(zip(mints, creators)):
        _launch(engine, m, c, f"Doge Rocket {i}", "DOGER", T0 + i * 10)
    feed_buyers(engine, mints[0], creators[0], 6, T0 + 40, 1.0, sol=0.12)
    state0 = engine.tokens[b58encode(mints[0])]
    report = engine.evaluate(state0, T0 + 50)
    narr = state0.narrativ
    assert narr["thema"] in ("doge", "rocket", "doger") and narr["n"] == 4 and narr["devs"] == 4 and narr["welle"]
    assert narr["position"] == 1 and narr["rang"] == 1 and narr["beobachtet"] == 4 and abs(narr["zufluss_thema_sol"] - 0.72) < 1e-6
    assert report.theme.startswith(narr["thema"]) and "WELLE" in report.theme and "Rang 1/4" in report.theme
    assert "Them " + report.theme in format_short(report) and engine.stats["in_welle"] == 1
    state1 = engine.tokens[b58encode(mints[1])]
    engine.evaluate(state1, T0 + 50)
    assert state1.narrativ["rang"] >= 2 and state1.narrativ["position"] == 2 and engine.stats["in_welle"] == 2
    rec = alert_record_extra(Alert(tier="GO", report=report, text="", state=state0), 2, "abc", "0.3.3", engine.cfg, engine.scoring)
    assert rec["narrativ"]["welle"] and rec["narrativ"]["rang"] == 1
    # ein Coin ohne zweiten Launch seines Begriffs hat kein Thema
    lone, lc = key(), key()
    _launch(engine, lone, lc, "Quiet Frog", "QF", T0 + 60)
    assert engine.evaluate(engine.tokens[b58encode(lone)], T0 + 61).theme is None


def test_metadata_terms_and_shared_source_become_the_theme():
    engine, _ = make_engine(stufe=2)
    m1, c1, m2, c2 = key(), key(), key(), key()
    _launch(engine, m1, c1, "Coin A", "AAA", T0)
    _launch(engine, m2, c2, "Coin B", "BBB", T0 + 5)
    engine.apply_metadata(engine.tokens[b58encode(m1)], {"description": "Elon just posted about tiffany lamps", "twitter": "https://x.com/elonmusk/status/123?s=20"}, T0 + 2)
    s2 = engine.tokens[b58encode(m2)]
    engine.apply_metadata(s2, {"description": "TIFFANY lamp season", "twitter": "https://twitter.com/elonmusk/status/123"}, T0 + 7)
    assert s2.metadata_ok and s2.metadata["description"].startswith("TIFFANY")
    narr = engine._theme_check(s2, T0 + 8)
    assert narr["thema"] == "tiffany" and narr["n"] == 2 and narr["devs"] == 2 and not narr["welle"]
    assert narr["quelle"] == {"anker": "x.com/elonmusk/status/123", "n": 2, "devs": 2}
    assert theme_line(narr).endswith("Quelle ×2") and theme_line(None) is None
    engine.apply_metadata(s2, "kein dict", T0 + 9)  # wird ignoriert


def test_watch_list_alerts_at_launch_and_from_the_description():
    engine, alerts = make_engine(stufe=2)
    engine.cfg.watch_terms = ("TIFFANY",)
    m1, c1 = key(), key()
    _launch(engine, m1, c1, "Tiffany Blue", "TIFF", T0)
    assert [a.tier for a in alerts] == ["WATCH"] and alerts[0].text.startswith("👁️ WATCH") and "Beobachtungsliste: tiffany (Name)" in alerts[0].text
    assert engine.stats["watch"] == 1 and "WATCH" in engine.tokens[b58encode(m1)].tiers_sent
    m2, c2 = key(), key()
    _launch(engine, m2, c2, "TIFFANYCOIN", "TC", T0 + 1)  # Begriff als Teil des Namens
    assert len(alerts) == 2 and "Them tiffany · 2 L/10min · 2 Devs" in alerts[1].text
    m3, c3 = key(), key()
    _launch(engine, m3, c3, "Blue Box", "BOX", T0 + 2)
    assert len(alerts) == 2
    st3 = engine.tokens[b58encode(m3)]
    engine.apply_metadata(st3, {"description": "the tiffany box"}, T0 + 4)
    engine.apply_metadata(st3, {"description": "the tiffany box"}, T0 + 5)  # nur einmal je Token
    assert len(alerts) == 3 and "(Beschreibung)" in alerts[2].text and alerts[2].report.word == "WATCH"
    engine2, alerts2 = make_engine(stufe=2)
    _launch(engine2, key(), key(), "Tiffany Blue", "TIFF", T0)
    assert alerts2 == [] and engine2.watch_hits("Tiffany") == set()
    args = build_parser().parse_args(["live", "--beobachte", "TIFFANY,blue box"])
    assert args.beobachte == "TIFFANY,blue box"


def test_latency_stats_in_the_tape_report():
    rows = [
        {"mint": "M", "seen_at": 1000.8, "ts": 1000, "backfill": False, "vS": 1, "vT": 1},
        {"mint": "M", "seen_at": 1010.0, "ts": 1001, "backfill": True, "vS": 1, "vT": 1},  # Backfill trägt die Alarmzeit, zählt nicht
        {"mint": "M", "seen_at": 1003.2, "ts": 1002, "backfill": False, "vS": 1, "vT": 1},
        {"mint": "M", "seen_at": 1005.5, "ts": 1003, "backfill": False, "vS": 1, "vT": 1},
    ]
    lat = latency_stats({"M": rows})
    assert lat == {"n": 3, "median_s": 1.2, "p90_s": 1.2}
    report = evaluate([], {"M": rows})
    assert report["latency"] == lat and "Latenz Empfang − Blockzeit" in format_report(report) and "im Rahmen" in format_report(report)
    slow = latency_stats({"M": [{"seen_at": 1003.5, "ts": 1000}]})
    assert slow["median_s"] == 3.5 and "strukturell spät" in format_report({**report, "latency": slow})
    assert latency_stats({}) == {"n": 0, "median_s": None, "p90_s": None}
