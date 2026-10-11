"""Wallet-Folge (0.3.8, OQ-035): Wallet-Liste, 🐋 FOLGE im Live-Modus, späte Coins, Papier-Strategien, Scout und Report."""
from __future__ import annotations

import json

from holder_scorer.calibrate import alert_record_extra, rules_hash
from holder_scorer.cli import build_parser, cmd_live, cmd_wallets
from holder_scorer.encoding import b58encode
from holder_scorer.extern import TIER_RANK, Extern, alert_groups, load_extern
from holder_scorer.folge import (
    WalletEntry,
    folge_suffix,
    format_wallet_line,
    format_wallet_report,
    parse_wallets_file,
    parse_wallets_line,
    scout,
    scout_lines,
    wallet_report,
    wallets_file_hash,
)
from holder_scorer.live import LiveConfig
from holder_scorer.paper import STRATEGIES, load_paper
from tests.helpers import key
from tests.test_fair import TIERS, _standard_flow
from tests.test_live import T0, feed_buyers, launch_msg, make_engine, trade_logs
from tests.test_paper import make_paper_engine, run_ticks

W1 = b58encode(key())
W2 = b58encode(key())
FOLGE_TIERS = TIERS + ("FOLGE",)


# --- Liste -----------------------------------------------------------------------------------------------------------
def test_parse_wallets_file_and_roundtrip(tmp_path):
    f = tmp_path / "wallets.txt"
    f.write_text(
        "# Kommentar\n"
        f"{W1} Narrativ-Käufer # Solscan 2026-10-11, früh in BONK-Welle\n"
        f"{W2} scout 4/7  # Wilson 29%–83%\n"
        "nichtgültig Tag\n"
        f"{W1} 2/5\n",  # Duplikat: ergänzt die Statistik, behält Tag und Notiz
        encoding="utf-8",
    )
    wallets = parse_wallets_file(str(f))
    assert set(wallets) == {W1, W2}
    e1, e2 = wallets[W1], wallets[W2]
    assert e1.tag == "Narrativ-Käufer" and e1.notiz == "Solscan 2026-10-11, früh in BONK-Welle" and e1.quelle == "import"
    assert (e1.treffer, e1.coins) == (2, 5) and e1.stats_text() == "Treffer 2/5" and e1.name == "Narrativ-Käufer"
    assert e2.quelle == "scout" and e2.tag == "" and (e2.treffer, e2.coins) == (4, 7) and e2.name == e2.kurz
    assert format_wallet_line(e2) == f"{W2} scout 4/7  # Wilson 29%–83%"
    assert parse_wallets_line(format_wallet_line(e1)) == e1
    assert parse_wallets_line("zu kurz") is None and parse_wallets_line(f"{W1}") == WalletEntry(W1)
    assert len(wallets_file_hash(str(f))) == 12
    assert folge_suffix(e1, {"wallet": W1, "sol": 0.8, "bundle": False, "spaet": True}, "nach GO") == (
        "Wallet Narrativ-Käufer · Quelle import · Treffer 2/5 · Kauf 0.80 SOL · spät gesehen (Alter, Dev-Historie, Bundle unbekannt) · nach GO"
    )
    assert folge_suffix(None, {"wallet": W1, "sol": 0.1}) == f"Wallet {W1[:8]} · Kauf 0.10 SOL"


# --- Live: Kauf eines beobachteten Wallets in einem Coin im Blick -------------------------------------------------------
def _follow_engine(stufe=2, tiers=FOLGE_TIERS, side=None, entries=None):
    engine, alerts = make_engine(stufe=stufe, tiers=tiers, side=side)
    engine.follow = entries or {W1: WalletEntry(W1, tag="Smart", quelle="scout", treffer=3, coins=7)}
    engine.cfg.follow_hash = "abc123def456"
    return engine, alerts


def test_folge_alert_on_a_tracked_coin_with_context_and_record():
    engine, alerts = _follow_engine()
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    m58 = b58encode(mint)
    # the dev's own buy never counts, even when the dev is on the list
    engine.follow[b58encode(creator)] = WalletEntry(b58encode(creator), tag="Dev")
    engine.on_logs(m58, 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
    engine.tick(T0 + 6)
    assert alerts == []
    # the watched wallet buys through the mint subscription: FOLGE with the next scored evaluation
    engine.on_logs(m58, 5020, "w1buy", None, trade_logs(mint, key_from(W1), 0.8, 800_000.0, True, int(T0 + 8), creator), now=T0 + 8)
    engine.tick(T0 + 9)
    assert [a.tier for a in alerts] == ["FOLGE"]
    a = alerts[0]
    assert a.report.word == "FOLGE" and a.report.verdict is not None and a.text.startswith("🐋 FOLGE")
    head = a.text.splitlines()[0]
    assert "Wallet Smart · Quelle scout · Treffer 3/7 · Kauf 0.80 SOL" in head and "spät" not in head
    assert a.text.splitlines()[-1] == f"Wallet solscan.io/account/{W1}"
    st = engine.tokens[m58]
    assert st.folge["wallet"] == W1 and st.folge["sol"] == 0.8 and st.folge["tag"] == "Smart" and st.folge["liste"] == "abc123def456"
    assert st.folge["spaet"] is False and st.folge["alter_s"] == 8.0 and st.folge["weitere"] == [] and st.folge_at == T0 + 8
    rec = alert_record_extra(a, 2, "h", "0.3.8", engine.cfg, engine.scoring)
    assert rec["tier"] == "FOLGE" and rec["folge"]["wallet"] == W1 and rec["spaet"] is False
    assert engine.stats["folge"] == 1
    # a second buy of the same wallet is appended, not alerted again; a second watched wallet likewise
    engine.follow[W2] = WalletEntry(W2)
    engine.on_logs(m58, 5030, "w1buy2", None, trade_logs(mint, key_from(W1), 0.2, 200_000.0, True, int(T0 + 12), creator), now=T0 + 12)
    engine.on_logs(m58, 5031, "w2buy", None, trade_logs(mint, key_from(W2), 0.3, 300_000.0, True, int(T0 + 13), creator), now=T0 + 13)
    engine.tick(T0 + 14)
    assert [a.tier for a in alerts] == ["FOLGE"] and [b["wallet"] for b in st.folge["weitere"]] == [W1, W2]
    # a sale by the wallet is not a buy
    engine.on_logs(m58, 5040, "w1sell", None, trade_logs(mint, key_from(W1), 0.1, 100_000.0, False, int(T0 + 20), creator), now=T0 + 20)
    assert len(st.folge["weitere"]) == 2


def key_from(address: str) -> bytes:
    from holder_scorer.encoding import b58decode

    return b58decode(address)


def test_folge_after_go_and_min_sol_filter():
    engine, alerts = _follow_engine(entries={W1: WalletEntry(W1, tag="Smart")})
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]
    engine.cfg.folge_min_sol = 0.5
    engine.on_logs(b58encode(mint), 5400, "dust", None, trade_logs(mint, key_from(W1), 0.05, 50_000.0, True, int(T0 + 30), creator), now=T0 + 30)
    engine.tick(T0 + 31)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]  # below --folge-min-sol
    engine.on_logs(b58encode(mint), 5410, "real", None, trade_logs(mint, key_from(W1), 1.0, 900_000.0, True, int(T0 + 33), creator), now=T0 + 33)
    engine.tick(T0 + 34)
    assert [a.tier for a in alerts] == ["BLICK", "GO", "FOLGE"] and "· nach GO" in alerts[2].text.splitlines()[0]
    # without FOLGE among the tiers nothing is sent, the buy is still noted on the token
    engine2, alerts2 = _follow_engine(tiers=TIERS, entries={W1: WalletEntry(W1)})
    m2, c2 = key(), key()
    engine2.on_launch(launch_msg(m2, c2), now=T0)
    engine2.on_logs(b58encode(m2), 5000, "b", None, trade_logs(m2, key_from(W1), 0.8, 800_000.0, True, int(T0 + 5), c2), now=T0 + 5)
    engine2.tick(T0 + 6)
    assert alerts2 == [] and engine2.tokens[b58encode(m2)].folge is not None


# --- Live: Kauf in einem Coin, den der Bot nie als Launch sah (Wallet-Abo) -------------------------------------------------
def test_wallet_logs_build_a_late_state_and_alert_without_any_verdict_or_fetch():
    engine, alerts = _follow_engine()
    mint, creator = key(), key()
    m58 = b58encode(mint)
    logs = trade_logs(mint, key_from(W1), 0.8, 800_000.0, True, int(T0 + 100), creator)
    new, mute = engine.on_wallet_logs(W1, 7000, "wbuy", None, logs, now=T0 + 100)
    assert new == [m58] and not mute
    st = engine.tokens[m58]
    assert st.spaet and st.creator == b58encode(creator) and st.curve is not None and st.create_slot_known and st.create.slot == 0
    assert st.missing_sigs == [] and engine.stats["spaet"] == 1 and engine.stats["wallet_logs"] == 1
    engine.tick(T0 + 101)
    assert [a.tier for a in alerts] == ["FOLGE"] and "spät gesehen" in alerts[0].text.splitlines()[0]
    assert alerts[0].report.verdict is not None  # scored, so the record carries curve, slot and features
    rec = alert_record_extra(alerts[0], 2, "h", "0.3.8", engine.cfg, engine.scoring)
    assert rec["spaet"] is True and rec["folge"]["alter_s"] is None
    # the same transaction arriving through the mint subscription is not a second trade
    before = len(st.trades)
    assert engine.on_logs(m58, 7000, "wbuy", None, logs, now=T0 + 100.5) == 0 and len(st.trades) == before
    # many outside buyers later: still no BLICK/GO/RUG for a coin seen this late, and no side checks
    feed_buyers(engine, mint, creator, 16, T0 + 103, 1.0, sol=0.15, slot0=7010)
    engine.tick(T0 + 125)
    engine.tick(T0 + 131)
    assert [a.tier for a in alerts] == ["FOLGE"] and st.pending == set() and st.done == set()
    # other activity of the wallet (transfers, other DEXes) is dropped without a fetch
    new2, _ = engine.on_wallet_logs(W1, 7100, "transfer", None, ["Program 11111111111111111111111111111111 invoke [1]", "Program 11111111111111111111111111111111 success"], now=T0 + 140)
    assert new2 == [] and engine.stats["wallet_fremd"] == 1 and st.missing_sigs == []
    assert engine.on_wallet_logs(W1, 7101, "failed", {"err": 1}, logs, now=T0 + 141) == ([], False)
    # the coin stays in view for folge_keep_s although track_seconds passed, then expires
    assert engine.tick(T0 + 100 + 600) == [] and m58 in engine.tokens
    assert m58 in engine.tick(T0 + 100 + 1801)


def test_hyperactive_wallet_is_muted_and_a_full_engine_drops_late_coins():
    engine, alerts = _follow_engine()
    engine.cfg.folge_max_logs_h = 3
    creator = key()
    for i in range(3):
        engine.on_wallet_logs(W1, 7000 + i, f"s{i}", None, trade_logs(key(), key_from(W1), 0.1, 100_000.0, True, int(T0 + i), creator), now=T0 + i)
    new, mute = engine.on_wallet_logs(W1, 7010, "s4", None, trade_logs(key(), key_from(W1), 0.1, 100_000.0, True, int(T0 + 4), creator), now=T0 + 4)
    assert mute and new == [] and W1 in engine.follow_muted and engine.stats["wallet_stumm"] == 1
    assert engine.on_wallet_logs(W1, 7011, "s5", None, [], now=T0 + 5) == ([], False) and engine.stats["wallet_logs"] == 4
    # a new hour resets the counter for another wallet
    engine.follow[W2] = WalletEntry(W2)
    engine.on_wallet_logs(W2, 8000, "a", None, [], now=T0)
    engine.on_wallet_logs(W2, 8001, "b", None, [], now=T0 + 3700)
    assert engine.follow_logs[W2] == (T0 + 3700, 1)
    engine.cfg.max_tracked = len(engine.tokens)
    new, _ = engine.on_wallet_logs(W2, 8002, "c", None, trade_logs(key(), key_from(W2), 0.1, 100_000.0, True, int(T0 + 3701), creator), now=T0 + 3701)
    assert new == [] and engine.stats["dropped_full"] == 1


# --- Papier -----------------------------------------------------------------------------------------------------------
def test_paper_folge_strategy_enters_on_a_late_coin_and_closes_at_the_cap(tmp_path):
    hold = next(s for s in STRATEGIES if s.name == "FOLGE-halten")
    engine, trader, alerts = make_paper_engine(tmp_path, strategies=[hold])
    engine.cfg.tiers = FOLGE_TIERS
    engine.follow = {W1: WalletEntry(W1, tag="Smart")}
    mint, creator = key(), key()
    m58 = b58encode(mint)
    engine.on_wallet_logs(W1, 7000, "wbuy", None, trade_logs(mint, key_from(W1), 0.8, 800_000.0, True, int(T0), creator), now=T0)
    run_ticks(engine, trader, T0 + 1, T0 + 5)
    assert [a.tier for a in alerts] == ["FOLGE"] and trader.stats["kauf"] == 1 and (hold.name, m58) in trader.positions
    run_ticks(engine, trader, T0 + 6, T0 + 1900, step=5.0)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    buy = next(r for r in recs if r["typ"] == "kauf")
    sell = next(r for r in recs if r["typ"] == "verkauf")
    assert buy["strategie"] == "FOLGE-halten" and buy["ausloeser"].startswith("FOLGE") and sell["grund"].split(" ")[0] in ("ZEIT", "ENDE")
    assert m58 not in engine.tokens
    assert {s.name for s in STRATEGIES if s.entry == "FOLGE"} == {"FOLGE-halten", "FOLGE-trail", "FOLGE-2x"}


# --- Scout und Report -------------------------------------------------------------------------------------------------
def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _tape_rows(mint, t0, dev, buyers, control=False):
    rows = [{"mint": mint, "t0": t0, "ts": int(t0), "slot": 100, "user": dev, "buy": True, "sol": 500_000_000, "tok": 10**13, "dev": dev, "control": control, "vS": 30_500_000_000, "vT": 10**15}]
    for i, (user, dt) in enumerate(buyers):
        rows.append({"mint": mint, "t0": t0, "ts": int(t0 + dt), "slot": 100 + 4 + i, "user": user, "buy": True, "sol": 80_000_000, "tok": 8 * 10**11, "dev": dev, "control": control, "vS": 30_600_000_000, "vT": 10**15 - 10**12})
    return rows


def test_scout_finds_early_buyers_of_good_coins_and_excludes_bots(tmp_path):
    smart, bot, late, dev = W1, W2, b58encode(key()), b58encode(key())
    t0 = T0
    goods = [b58encode(key()) for _ in range(7)]  # the smart wallet was early in all of them
    bads = [b58encode(key()) for _ in range(8)]  # early only in the first one; the last one has no usable label
    ctrls = [b58encode(key()) for _ in range(3)]  # one survives
    rows = []
    t = t0
    for i, m in enumerate(goods):
        rows += _tape_rows(m, t, dev, [(smart, 10 + i), (bot, 5)] + ([(late, 120)] if i == 0 else []))
        t += 600
    for i, m in enumerate(bads):
        rows += _tape_rows(m, t, dev, [(bot, 5)] + ([(smart, 15)] if i == 0 else []))
        t += 600
    for m in ctrls:
        rows += _tape_rows(m, t, dev, [(bot, 5)], control=True)
        t += 600
    tape = tmp_path / "tape.jsonl"
    _write_jsonl(tape, rows)
    nl = lambda m, liq, dex="pumpfun": {"typ": "nachlauf", "t": t0 + 90_000, "mint": m, "nach_s": 86400, "alter_s": 86400, "dex": dex, "liq_usd": liq, "preis_native": 1e-7}
    extern_rows = [{"typ": "feed", "t": t0 - 10, "ereignis": "verbunden"}, {"typ": "graduierung", "t": t0 + 400, "mint": goods[0], "alarm": "GO"}]
    extern_rows += [nl(m, 5000.0, "pumpswap") for m in goods[1:]]
    extern_rows += [nl(m, 100.0) for m in bads[:-1]]
    extern_rows += [{"typ": "nachlauf", "t": t0 + 90_000, "mint": bads[-1], "nach_s": 86400, "alter_s": 86400, "fehlt": True}]
    extern_rows += [nl(ctrls[0], 3000.0), nl(ctrls[1], 10.0), nl(ctrls[2], 10.0), {"typ": "feed", "t": t0 + 100_000, "ereignis": "getrennt"}]
    aussen = tmp_path / "aussen.jsonl"
    _write_jsonl(aussen, extern_rows)
    ex = load_extern(str(aussen))
    res = scout(str(tape), ex, min_coins=2, max_anteil=0.5)
    # the last bad coin has no usable label (fehlt is not dead): 17 of 18 coins are judgeable, 3 of them controls
    assert res.coins == 18 and res.beurteilbar == 17 and res.kontrollen == 3 and res.kontroll_rate == 1 / 3
    assert res.grundrate_alle == 8 / 17 and res.bots == 1  # the bot was early in every coin
    assert [c["wallet"] for c in res.kandidaten] == [smart]
    c = res.kandidaten[0]
    assert (c["treffer"], c["coins"], c["frueh_in"]) == (7, 8, 8) and c["seit"] == t0 + 10 and c["wilson"][0] > 8 / 17
    assert "Grundrate aller getapeten Coins" in res.lesart  # fewer than 20 controls: the bar is the overall rate
    lines = scout_lines(res, now=t0)
    assert lines[0].startswith("# wallets scout") and lines[1].startswith(f"{smart} scout 7/8  # Wilson")
    # the late buyer (120 s) is not early, a stricter window drops the smart wallet's second coin
    strict = scout(str(tape), ex, frueh_s=12.0, min_coins=1, max_anteil=0.5)
    assert late not in {c["wallet"] for c in strict.kandidaten}
    # CLI: scout writes the list, zeigen reads it back
    out = tmp_path / "wallets.txt"
    args = build_parser().parse_args(["wallets", "scout", str(tape), "--extern", str(aussen), "--min-coins", "2", "--max-anteil", "0.5", "--out", str(out)])
    assert cmd_wallets(args) == 0 and parse_wallets_file(str(out))[smart].quelle == "scout"
    assert cmd_wallets(build_parser().parse_args(["wallets", "zeigen", str(out)])) == 0
    (tmp_path / "leer.jsonl").write_text("", encoding="utf-8")
    empty = scout(str(tmp_path / "leer.jsonl"), ex)
    assert empty.coins == 0 and "Tape leer" in empty.lesart


def test_wallet_report_multiples_and_cli(tmp_path):
    mint_a, mint_b, mint_c = (b58encode(key()) for _ in range(3))
    curve = {"virtual_quote_reserves": 32_000_000_000, "virtual_token_reserves": 10**15}  # 32 SOL / 1e9 Token = 3.2e-8 SOL je Token
    records = [
        {"mint": mint_a, "tier": "FOLGE", "alert_at": T0, "launch_received_at": T0 - 20, "slot": 100, "rules_hash": "h", "curve": curve, "folge": {"wallet": W1}, "spaet": False},
        {"mint": mint_a, "tier": "GO", "alert_at": T0 + 5, "launch_received_at": T0 - 20, "slot": 101, "rules_hash": "h", "curve": curve},
        {"mint": mint_b, "tier": "FOLGE", "alert_at": T0 + 100, "launch_received_at": T0, "slot": 200, "rules_hash": "h", "curve": curve, "folge": {"wallet": W1}, "spaet": True},
        {"mint": mint_c, "tier": "FOLGE", "alert_at": T0 + 200, "launch_received_at": T0, "slot": 300, "rules_hash": "h", "curve": curve, "folge": {"wallet": W2}},
    ]
    extern_rows = [
        {"typ": "feed", "t": T0 - 10, "ereignis": "verbunden"},
        {"typ": "graduierung", "t": T0 + 900, "mint": mint_a, "alarm": "GO"},
        {"typ": "nachlauf", "t": T0 + 3600, "mint": mint_a, "nach_s": 3600, "alter_s": 3600, "dex": "pumpswap", "liq_usd": 20_000.0, "preis_native": 6.4e-8},
        {"typ": "nachlauf", "t": T0 + 86400, "mint": mint_a, "nach_s": 86400, "alter_s": 86400, "dex": "pumpswap", "liq_usd": 20_000.0, "preis_native": 1.28e-7},
        {"typ": "nachlauf", "t": T0 + 3700, "mint": mint_b, "nach_s": 3600, "alter_s": 3600, "dex": "pumpfun", "liq_usd": 50.0, "preis_native": 1e-8},
        {"typ": "nachlauf", "t": T0 + 86500, "mint": mint_b, "nach_s": 86400, "alter_s": 86400, "fehlt": True},
        {"typ": "feed", "t": T0 + 200_000, "ereignis": "getrennt"},
    ]
    aussen = tmp_path / "aussen.jsonl"
    _write_jsonl(aussen, extern_rows)
    ex = load_extern(str(aussen))
    rep = wallet_report(records, ex, {W1: WalletEntry(W1, tag="Smart", treffer=3, coins=7)}, fee_bps=0)
    w1 = rep["wallets"][W1]
    assert w1["alarme"] == 2 and w1["spaet"] == 1 and w1["tag"] == "Smart" and w1["liste"] == "Treffer 3/7"
    assert w1["graduation"]["k"] == 1 and w1["graduation"]["n"] == 2
    h1, h24 = w1["nach_3600"], w1["nach_86400"]
    # mint_a doubled after 1 h and quadrupled after 24 h; mint_b is unsellable (liq 50 USD), later missing
    assert h1["n"] == 2 and h1["lebt"] == 1 and h1["median_x"] == 2.0 and h1["anteil_ueber_1x"] == 1.0 and h1["median_x_konservativ"] == 1.0
    assert h24["n"] == 2 and h24["lebt"] == 1 and h24["median_x"] == 4.0 and h24["median_x_konservativ"] == 2.0
    w2 = rep["wallets"][W2]
    assert w2["alarme"] == 1 and w2["liste"] == "nicht in der Liste" and w2["nach_3600"]["n"] == 0
    text = format_wallet_report(rep)
    assert "Smart (" in text and "+1 h: lebt 1/2" in text and "Median 2.00x" in text and "noch kein Nachlauf" in text
    assert format_wallet_report({"wallets": {}, "horizonte": [], "fee_bps": 0}).startswith("Keine FOLGE-Alarme")
    with_fee = wallet_report(records, ex, None)["wallets"][W1]["nach_3600"]["median_x"]
    assert 1.9 < with_fee < 2.0  # 1.25 % per side
    recs = tmp_path / "live.jsonl"
    _write_jsonl(recs, [{**r, "recorded_at": r["alert_at"], "label": "x", "features": {}, "outcome": None} for r in records])
    lst = tmp_path / "w.txt"
    lst.write_text(f"{W1} Smart 3/7\n", encoding="utf-8")
    args = build_parser().parse_args(["wallets", "report", str(recs), "--extern", str(aussen), "--wallets", str(lst), "--horizonte", "3600,86400"])
    assert cmd_wallets(args) == 0
    # FOLGE is part of the shared tier ranking, at the bottom: a coin with GO stays in the GO group
    assert TIER_RANK["FOLGE"] == 0 and alert_groups(str(recs))[mint_a][0] == "GO" and alert_groups(str(recs))[mint_c][0] == "FOLGE"


# --- CLI und Regel-Hash -----------------------------------------------------------------------------------------------
def test_live_cli_wallets_flags_and_rules_hash(tmp_path):
    args = build_parser().parse_args(["live", "--wallets", "w.txt", "--folge-min-sol", "0.2", "--folge-halten", "900"])
    assert args.wallets == "w.txt" and args.folge_min_sol == 0.2 and args.folge_halten == 900.0
    assert cmd_live(build_parser().parse_args(["live", "--rpc", "http://localhost:1", "--wallets", str(tmp_path / "fehlt.txt")])) == 2
    empty = tmp_path / "leer.txt"
    empty.write_text("# nur Kommentar\n", encoding="utf-8")
    assert cmd_live(build_parser().parse_args(["live", "--rpc", "http://localhost:1", "--wallets", str(empty)])) == 2
    base, scoring = LiveConfig.for_stufe(2)
    with_follow, _ = LiveConfig.for_stufe(2)
    with_follow.follow_path, with_follow.follow_hash, with_follow.folge_keep_s, with_follow.folge_min_sol = "w.txt", "abc", 900.0, 0.2
    assert rules_hash(base, scoring, "0.3.8") == rules_hash(with_follow, scoring, "0.3.8")
    assert Extern().beurteilbar(T0) is False
