"""Außenquellen (0.3.6, OQ-033): Migrationsfeed, Rugcheck, Nachlauf, Report, Profil, CLI – alles offline mit Fakes."""
from __future__ import annotations

import json

from holder_scorer import extern as ex
from holder_scorer import profile as pf
from holder_scorer.cli import build_parser, cmd_live, cmd_quellen
from holder_scorer.dexpaid import BASE_URL, TOKENS
from holder_scorer.encoding import b58encode
from holder_scorer.pump import TRADE_EVENT_DISC
from holder_scorer.replay import evaluate, format_report, report_to_json
from tests.helpers import fake_tx, key, trade_event_bytes
from tests.test_dexpaid import pair
from tests.test_fair import _standard_flow
from tests.test_live import T0, make_engine
from tests.test_profile import HistoryRpc, V_TOK0
from tests.test_replay import row as tape_row

TIERS = ("BLICK", "GO", "WIDERRUF", "RUG", "GESPERRT")


def _rows(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_parse_migration_only_non_launch_messages():
    m = "M" * 44
    assert ex.parse_migration({"mint": m, "txType": "create"}) is None
    assert ex.parse_migration({"mint": m}) is None  # ohne txType bleibt es ein Launch (accept_launch)
    assert ex.parse_migration({"mint": m, "txType": "buy"}) is None
    assert ex.parse_migration({"mint": "kurz", "txType": "migrate"}) is None
    assert ex.parse_migration({"mint": m, "pool": "pump"}) is None  # ohne txType auf dem pump-Pool: Launch
    assert ex.parse_migration({"mint": m, "pool": "pump-amm"})["typ"] == "graduierung"  # ohne txType, fremder Pool: Migration
    assert ex.parse_migration({"mint": m, "txType": "create", "pool": "bonk"}) is None  # fremder Launchpad-Launch: kein Launch, keine Migration
    row = ex.parse_migration({"mint": m, "txType": "migrate", "pool": "pump-amm", "signature": "s1"}, now=T0)
    assert row["typ"] == "graduierung" and row["mint"] == m and row["t"] == T0 and row["alarm"] is None
    assert row["roh"]["pool"] == "pump-amm" and row["signature"] == "s1"


def test_engine_counts_migrations_and_joins_them_to_own_alerts(tmp_path):
    engine, alerts = make_engine(stufe=2, tiers=TIERS)
    engine.cfg.extern_path = str(tmp_path / "aussen.jsonl")
    engine.on_feed("verbunden", now=T0 - 10)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]
    m58 = b58encode(mint)
    engine.tick(T0 + 600)
    assert m58 not in engine.tokens  # zur Migration ist der Token längst aus dem Blick
    assert engine.on_migration({"mint": m58, "txType": "migrate", "pool": "pump-amm"}, now=T0 + 900)
    assert not engine.on_migration({"mint": b58encode(key()), "txType": "create"}, now=T0 + 901)
    assert engine.on_migration({"mint": b58encode(key()), "txType": "migrate"}, now=T0 + 902)
    assert engine.stats["graduierungen"] == 2 and engine.stats["graduierungen_alarm"] == 1
    rows = _rows(tmp_path / "aussen.jsonl")
    assert rows[0] == {"typ": "feed", "t": T0 - 10, "ereignis": "verbunden"}
    grads = [r for r in rows if r["typ"] == "graduierung"]
    assert [g["alarm"] for g in grads] == ["GO", None] and grads[0]["mint"] == m58 and grads[0]["roh"]["txType"] == "migrate"
    # Alarm-Gedächtnis: höchster Tier je Mint, begrenzt
    engine._remember_alert(m58, "BLICK")
    assert engine.recent_alerts[m58] == "GO"
    for i in range(ex.RECENT_ALERTS_MAX + 5):
        engine._remember_alert(f"X{i}", "BLICK")
    assert len(engine.recent_alerts) == ex.RECENT_ALERTS_MAX and m58 not in engine.recent_alerts
    loaded = ex.load_extern(str(tmp_path / "aussen.jsonl"))
    assert loaded.graduiert[m58] == T0 + 900 and loaded.alarm_bei_graduierung[m58] == "GO"
    assert loaded.erster_t == T0 - 10 and loaded.letzter_t == T0 + 902 and loaded.zaehler == {"feed": 1, "graduierung": 2}
    text = ex.describe_extern(loaded)
    assert "2 Graduierungen, davon mit eigenem Alarm 1" in text and m58 in text


def test_rugcheck_rows_and_engine_queries_once_per_token(tmp_path):
    m = "M" * 44

    def api_ok(url):
        assert url == ex.RUGCHECK_URL.format(mint=m)
        return 200, {"score": 1234, "score_normalised": 42, "rugged": False, "risks": [{"name": "Mint Authority", "level": "danger", "score": 1000}]}

    row = ex.rugcheck_fetch(m, fetch=api_ok, now=T0)
    assert row["typ"] == "risiko" and row["score_norm"] == 42 and row["score"] == 1234 and row["rugged"] is False
    assert row["risiken"] == [{"name": "Mint Authority", "level": "danger", "score": 1000}] and "roh" not in row
    assert ex.rugcheck_fetch(m, fetch=lambda u: (404, None))["fehlt"] is True

    def boom(url):
        raise RuntimeError("netz weg")

    bad = ex.rugcheck_fetch(m, fetch=boom)
    assert bad["fehlt"] and bad["status"] == 0 and "netz weg" in bad["fehler"]
    odd = ex.rugcheck_fetch(m, fetch=lambda u: (200, {"something": 1}))
    assert odd["roh"] == {"something": 1} and odd["score_norm"] is None and "fehlt" not in odd

    calls: list[tuple[str, str]] = []

    def side(name, fn, done, delay=0.0, group="rpc"):
        calls.append((name, group))
        try:
            result = fn()
        except Exception:  # noqa: BLE001 - wie der echte Runner: Fehler → None
            result = None
        done(result)

    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=side)
    engine.cfg.extern_path = str(tmp_path / "aussen.jsonl")
    engine.cfg.rugcheck = True
    engine.cfg.fair.require_metadata = engine.cfg.fair.require_creator_check = False  # mit Nebenabfragen, aber ohne Metadaten-URI: sonst GESPERRT statt GO
    engine.rugcheck_fetch = lambda mint: ex.rugcheck_fetch(mint, fetch=lambda u: (200, {"score_normalised": 7, "risks": []}), now=T0)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]
    engine.tick(T0 + 31)
    assert [c for c in calls if c[0] == "rugcheck"] == [("rugcheck", "http")]  # einmal je Token, HTTP-Gruppe ohne RPC-Budget
    risk = [r for r in _rows(tmp_path / "aussen.jsonl") if r["typ"] == "risiko"]
    assert len(risk) == 1 and risk[0]["alarm"] == "GO" and risk[0]["score_norm"] == 7 and risk[0]["mint"] == b58encode(mint)
    # ohne --rugcheck keine Abfrage
    engine2, alerts2 = make_engine(stufe=2, tiers=TIERS, side=side)
    engine2.cfg.extern_path = str(tmp_path / "aussen2.jsonl")
    engine2.cfg.fair.require_metadata = engine2.cfg.fair.require_creator_check = False
    calls.clear()
    _standard_flow(engine2, key(), key())
    assert [a.tier for a in alerts2] == ["BLICK", "GO"] and not [c for c in calls if c[0] == "rugcheck"]


def _records_and_tape(tmp_path, n: int = 35):
    T = 1_800_000_000.0
    mints = [(f"{i:02d}" + "X" * 42) for i in range(n)]
    records = tmp_path / "live.jsonl"
    with open(records, "w", encoding="utf-8") as fh:
        for i, m in enumerate(mints):
            fh.write(json.dumps({"mint": m, "recorded_at": T + i, "label": "JA", "tier": "BLICK", "alert_at": T + i, "slot": 1}) + "\n")
            if i % 2 == 0:
                fh.write(json.dumps({"mint": m, "recorded_at": T + i + 5, "label": "JA", "tier": "GO", "alert_at": T + i + 5, "slot": 2}) + "\n")
    control = "C" * 44
    tape = tmp_path / "tape.jsonl"
    with open(tape, "w", encoding="utf-8") as fh:
        for m in (control, mints[0]):  # mints[0] hat einen Alarm und zählt nicht als Kontrolle
            fh.write(json.dumps({"mint": m, "seen_at": T + 1, "t0": T, "control": True, "vS": 1, "vT": 1}, separators=(",", ":")) + "\n")
    return T, mints, control, records, tape


def test_nachlauf_fetch_batches_due_mints_and_is_idempotent(tmp_path):
    T, mints, control, records, tape = _records_and_tape(tmp_path)
    out = tmp_path / "aussen.jsonl"
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        assert url.startswith(BASE_URL + TOKENS)
        ms = url[len(BASE_URL + TOKENS):].split(",")
        assert len(ms) <= 30
        pairs = []
        for m in ms:
            if m == control:
                continue  # Kontrolle ohne Paar
            p = pair(m, 1.0, liq=5000.0)
            p["dexId"] = "pumpswap" if m == mints[0] else "pumpfun"
            pairs.append(p)
        return 200, {"pairs": pairs}

    now = T + 3600 + 100  # +1 h fällig, +24 h noch nicht
    groups = ex.alert_groups(str(records))
    assert groups[mints[0]] == ("GO", T) and groups[mints[1]] == ("BLICK", T + 1)
    assert ex.control_groups(str(tape), exclude=groups) == {control: ("KONTROLLE", T)}
    dry = ex.nachlauf_fetch(str(records), str(out), tape_path=str(tape), fetch=fetch, now=now, dry_run=True)
    assert dry["ziele"] == 36 and dry["faellig"] == 36 and dry["je_gruppe"] == {"GO": 18, "BLICK": 17, "KONTROLLE": 1}
    assert dry["je_horizont"] == {"3600": 36} and dry["anfragen_geplant"] == 2 and not out.exists() and calls == []
    assert "Trockenlauf: 2 DexScreener-Anfragen" in ex.format_nachlauf_stats(dry, dry_run=True)
    stats = ex.nachlauf_fetch(str(records), str(out), tape_path=str(tape), fetch=fetch, now=now, sleep=lambda s: None)
    assert stats["anfragen"] == 2 and stats["zeilen"] == 36 and stats["fehlend"] == 1 and stats["limit"] == 0
    assert control in calls[-1] and control not in calls[0]  # Alarme vor Kontrollen
    rows = _rows(out)
    assert len(rows) == 36 and all(r["typ"] == "nachlauf" and r["nach_s"] == 3600.0 and "ereignis" not in r for r in rows)
    k = next(r for r in rows if r["mint"] == control)
    assert k["gruppe"] == "KONTROLLE" and k["fehlt"] is True and k["t_ref"] == T
    g = next(r for r in rows if r["mint"] == mints[0])
    assert g["gruppe"] == "GO" and g["dex"] == "pumpswap" and g["liq_usd"] == 5000.0 and g["alter_s"] == 3700
    again = ex.nachlauf_fetch(str(records), str(out), tape_path=str(tape), fetch=fetch, now=now)
    assert again["faellig"] == 0 and again["anfragen"] == 0  # idempotent
    now2 = T + 86400 + 100  # alle 35 Alarme (t_ref bis T + 34) und die Kontrolle sind für +24 h fällig
    limited = ex.nachlauf_fetch(str(records), str(out), tape_path=str(tape), fetch=lambda u: (429, None), now=now2)
    assert limited["limit"] == 1 and limited["anfragen"] == 1 and limited["zeilen"] == 0
    part = ex.nachlauf_fetch(str(records), str(out), tape_path=str(tape), fetch=fetch, now=now2, max_mints=5)
    assert part["faellig"] == 36 and part["geplant"] == 5 and part["zeilen"] == 5 and part["anfragen"] == 1
    rest = ex.nachlauf_fetch(str(records), str(out), tape_path=str(tape), fetch=fetch, now=now2, sleep=lambda s: None)
    assert rest["faellig"] == 31 and rest["zeilen"] == 31
    loaded = ex.load_extern(str(out))
    assert loaded.dex_graduiert(mints[0]) and not loaded.dex_graduiert(mints[1]) and loaded.nachlauf_bekannt(mints[1]) and not loaded.nachlauf_bekannt(control)
    assert loaded.erster_t is None  # Nachlauf-Zeilen sagen nichts über die Laufzeit des Feeds
    args = build_parser().parse_args(["quellen", "nachlauf", str(records), "--extern", str(out), "--tape", str(tape), "--horizonte", "3600,86400", "--max", "5", "--dry-run"])
    assert args.max == 5 and args.je_minute == 250 and cmd_quellen(args) == 0
    assert cmd_quellen(build_parser().parse_args(["quellen", "zeigen", str(out)])) == 0


def _alert(mint: str, tier: str, t: float, slot: int) -> dict:
    return {"mint": mint, "tier": tier, "alert_at": t, "launch_received_at": t - 20.0, "slot": slot, "rules_hash": "h"}


def test_tape_report_with_extern_adds_outside_labels(tmp_path):
    T = 1_800_000_000
    g1, g2, b1, k1 = "G1" + "A" * 42, "G2" + "A" * 42, "B1" + "A" * 42, "K1" + "A" * 42
    up = dict(v_sol=45_000_000_000, v_tok=727_333_333_333_333, r_tok=447_433_333_333_333)
    tape = {
        g1: [tape_row(T, 10, mint=g1, t0=T - 5.0), tape_row(T + 300, 30, mint=g1, t0=T - 5.0, **up)],  # Anstieg vor dem Ausstieg +330 s
        g2: [tape_row(T, 10, mint=g2, t0=T - 5.0), tape_row(T + 400, 40, mint=g2, t0=T - 5.0)],
        b1: [tape_row(T, 10, mint=b1, t0=T - 5.0), tape_row(T + 400, 40, mint=b1, t0=T - 5.0)],
        k1: [tape_row(T, 10, mint=k1, t0=T - 5.0, control=True), tape_row(T + 400, 40, mint=k1, t0=T - 5.0, control=True)],
    }
    alerts = [_alert(g1, "BLICK", T + 1.0, 10), _alert(g1, "GO", T + 2.0, 10), _alert(g2, "GO", T + 2.0, 10), _alert(b1, "BLICK", T + 1.0, 10)]
    path = tmp_path / "aussen.jsonl"
    for row in [
        ex.feed_row("verbunden", T - 100_000),
        {"typ": "graduierung", "t": T + 5000, "mint": g1, "alarm": "GO", "roh": {}},
        {"typ": "graduierung", "t": T + 200_000, "mint": "Z" * 44, "alarm": None, "roh": {}},
        {"typ": "nachlauf", "t": T + 86_500, "mint": g1, "gruppe": "GO", "nach_s": 86400.0, "alter_s": 86_500, "dex": "pumpswap", "liq_usd": 5000.0, "mcap": 250_000.0},
        {"typ": "nachlauf", "t": T + 86_500, "mint": g2, "gruppe": "GO", "nach_s": 86400.0, "alter_s": 86_500, "dex": "pumpfun", "liq_usd": 100.0, "mcap": 4000.0},
        {"typ": "nachlauf", "t": T + 9_000, "mint": g2, "gruppe": "GO", "nach_s": 3600.0, "alter_s": 9_000, "dex": "pumpfun", "liq_usd": 3000.0},  # verspätet
        {"typ": "nachlauf", "t": T + 86_500, "mint": b1, "gruppe": "BLICK", "nach_s": 86400.0, "alter_s": 86_500, "fehlt": True},
        {"typ": "risiko", "t": T + 3, "mint": g1, "quelle": "rugcheck", "alarm": "GO", "status": 200, "score_norm": 10.0},
        {"typ": "risiko", "t": T + 3, "mint": g2, "quelle": "rugcheck", "alarm": "GO", "status": 200, "score_norm": 80.0},
    ]:
        ex.append_row(str(path), row)
    loaded = ex.load_extern(str(path))
    assert loaded.beurteilbar(T + 2.0) and not loaded.beurteilbar(T + 200_000) and loaded.luecken_s() == 0
    report = evaluate(alerts, tape, extern=loaded)
    e = report["extern"]
    assert e["feed"]["graduierungen"] == 2
    go = e["graduation"]["GO"]
    assert go["n"] == 2 and go["beurteilbar"] == 2 and go["offen"] == 0 and go["graduiert"] == 1 and go["anteil"] == 0.5 and go["tape_anteil"] == 0.0
    assert e["graduation"]["BLICK"] == {"n": 1, "beurteilbar": 1, "offen": 0, "graduiert": 0, "anteil": 0.0, "wilson": e["graduation"]["BLICK"]["wilson"], "tape_anteil": 0.0}
    assert e["graduation"]["KONTROLLE"]["n"] == 1 and e["graduation"]["KONTROLLE"]["graduiert"] == 0 and e["kontrollen_plausibel"] is None
    n24 = e["nachlauf"]["GO|86400"]
    assert n24["n"] == 2 and n24["ueberlebt"] == 1 and n24["anteil"] == 0.5 and n24["median_mcap"] == 250_000.0 and n24["verspaetet"] == 0
    assert e["nachlauf"]["GO|3600"]["n"] == 0 and e["nachlauf"]["GO|3600"]["verspaetet"] == 1
    assert e["nachlauf"]["BLICK|86400"]["ueberlebt"] == 0
    r = e["risiko"]
    assert r["go"] == 2 and r["abgefragt"] == 2 and r["mit_score"] == 2 and r["median_score"] == 45.0
    assert r["niedrig"] == {"n": 1, "treffer": 1, "wilson": r["niedrig"]["wilson"]} and r["hoch"]["treffer"] == 0 and r["lesart"].startswith("zu wenig")
    text = format_report(report)
    assert "Außenquellen (record-only, OQ-033)" in text and "Graduation GO" in text and "Nachlauf GO" in text and "Rugcheck: 2 von 2 GO" in text
    assert "Grundrate aller Launches 0.26–1.4 %" in text
    json.loads(report_to_json(report))
    plain = evaluate(alerts, tape)
    assert plain["extern"] is None and "Außenquellen" not in format_report(plain)
    args = build_parser().parse_args(["tape", "report", "r.jsonl", "t.jsonl", "--extern", str(path)])
    assert args.extern == str(path)


def test_profile_takes_graduated_coins_from_outside(tmp_path):
    mint, creator = key(), key()
    m58 = b58encode(mint)
    t0 = 1_800_000_000
    vsol, vtok = 30_500_000_000, V_TOK0
    sigs, txs = [], {}
    for i, dt in enumerate([0, 5, 12, 30, 400]):
        lam, raw = 100_000_000, 3_000_000_000_000
        vsol, vtok = vsol + lam, vtok - raw
        payer = key()
        ev = TRADE_EVENT_DISC + trade_event_bytes(mint, payer, lam, raw, True, t0 + dt, creator, reserves=(vsol, vtok))
        sigs.append({"signature": f"s{i}", "slot": 100 + i, "blockTime": t0 + dt, "err": None})
        txs[f"s{i}"] = fake_tx(f"s{i}", 100 + i, t0 + dt, payer, [ev])
    sigs.reverse()
    rpc = HistoryRpc(m58, sigs, txs)
    aussen = tmp_path / "aussen.jsonl"
    ex.append_row(str(aussen), {"typ": "graduierung", "t": t0 + 9000, "mint": m58, "alarm": None, "roh": {}})  # neueste zuerst
    ex.append_row(str(aussen), {"typ": "graduierung", "t": t0 + 6000, "mint": "Y" * 44, "alarm": None, "roh": {}})
    # Tape sagt „schlecht" (flache Kurve), die Graduation von außen ist die spätere Wahrheit → gut/extern ohne RPC
    taped = "T" * 44
    tape = tmp_path / "tape.jsonl"
    with open(tape, "w", encoding="utf-8") as fh:
        for ts, slot in ((t0, 10), (t0 + 100, 20), (t0 + 300, 30)):
            fh.write(json.dumps(tape_row(ts, slot, mint=taped, t0=float(t0))) + "\n")
    ex.append_row(str(aussen), {"typ": "graduierung", "t": t0 + 7000, "mint": taped, "alarm": "BLICK", "roh": {}})
    profile, text = pf.build_profile(tape_path=str(tape), extern_path=str(aussen), rpc=rpc, max_mints=1)
    src = profile["sources"]
    assert src["extern_graduierungen"] == 3 and src["extern_im_tape"] == 1 and src["extern_geladen"] == 1
    assert "1 Graduierungen wegen --max-mints 1 nicht geladen" in text and "Label-Herkunft: extern 2" in text
    assert rpc.stats["requests"] >= 1  # Historie über die Kurvenadresse (HistoryRpc prüft die Adresse)
    # ohne RPC: nur die Coins aus dem Tape bekommen das Außen-Label, der Rest wird benannt
    _, text2 = pf.build_profile(tape_path=str(tape), extern_path=str(aussen), rpc=None, max_mints=20)
    assert "2 Graduierungen nicht geladen: kein RPC" in text2 and "Label-Herkunft: extern 1" in text2
    args = build_parser().parse_args(["profil", "bauen", "--extern", str(aussen), "--out", str(tmp_path / "p.json"), "--dry-run"])
    assert args.extern == str(aussen)
    from holder_scorer.cli import cmd_profil

    assert cmd_profil(args) == 0 and not (tmp_path / "p.json").exists()


def test_live_cli_wires_extern_and_rugcheck():
    args = build_parser().parse_args(["live", "--extern", "aussen.jsonl", "--rugcheck"])
    assert args.extern == "aussen.jsonl" and args.rugcheck
    assert cmd_live(build_parser().parse_args(["live", "--rpc", "http://localhost:1", "--rugcheck"])) == 2  # --rugcheck braucht --extern
    from holder_scorer.calibrate import rules_hash
    from holder_scorer.live import LiveConfig

    cfg, scoring = LiveConfig.for_stufe(2)
    before = rules_hash(cfg, scoring, "0.3.6")
    cfg.extern_path, cfg.rugcheck, cfg.tape_path = "a.jsonl", True, "t.jsonl"
    assert rules_hash(cfg, scoring, "0.3.6") == before  # Dateinamen und record-only-Schalter ändern keine Regel
    cfg.fair.max_dev_share = 0.01
    assert rules_hash(cfg, scoring, "0.3.6") != before
