"""Paper trading: curve fills, entries per strategy, exits, path records, report and look-back."""
from __future__ import annotations

import json

from holder_scorer.encoding import b58encode
from holder_scorer.live import Alert, LiveConfig, LiveEngine
from holder_scorer.narrative import NameRegistry, narrative_score
from holder_scorer.paper import (
    CURVE_FEE_BPS,
    STRATEGIES,
    PaperTrader,
    buy_on_curve,
    curve_price,
    load_paper,
    look_back,
    paper_report,
    parse_calls_file,
    sell_on_curve,
    simulate_rule,
    strategies_by_name,
)
from holder_scorer.pump import TRADE_EVENT_DISC, BondingCurveState
from tests.helpers import fake_tx, key, trade_event_bytes
from tests.test_live import CURVES, T0, feed_buyers, launch_msg, trade_logs


def fresh_curve(vsol: int = 30_500_000_000, vtok: int = 1_073_000_000_000_000 - 20_000_000_000_000) -> BondingCurveState:
    return BondingCurveState(virtual_token_reserves=vtok, virtual_quote_reserves=vsol, real_token_reserves=vtok - 279_900_000_000_000, real_quote_reserves=vsol - 30_000_000_000, token_total_supply=10**15, complete=False)


def test_curve_fills_charge_fee_and_impact():
    curve = fresh_curve()
    tokens, paid, fee = buy_on_curve(curve, 80_000_000, CURVE_FEE_BPS)
    assert fee == 80_000_000 - paid and abs(fee / 80_000_000 - 0.0123) < 0.001  # 1.25 % of the curve amount
    assert 2_700_000_000_000 < tokens < 2_800_000_000_000  # about 2.76 M tokens at ~29 lamports per 1e6 raw
    after = BondingCurveState(curve.virtual_token_reserves - tokens, curve.virtual_quote_reserves + paid, curve.real_token_reserves - tokens, curve.real_quote_reserves + paid, 10**15, False)
    net, sell_fee = sell_on_curve(after, tokens, CURVE_FEE_BPS)
    loss = 1 - net / 80_000_000
    assert 0.024 < loss < 0.03  # two fees plus the position's own impact on a 30 SOL curve
    assert curve_price(curve) > 0 and buy_on_curve(curve, 0) == (0, 0, 0) and sell_on_curve(curve, 0) == (0, 0)


def make_paper_engine(tmp_path, strategies=None, stufe: int = 2, keywords=(), latency: float = 2.0):
    alerts: list[Alert] = []
    cfg, scoring = LiveConfig.for_stufe(stufe)
    trader = PaperTrader(strategies or list(STRATEGIES), size_sol=0.08, latency_s=latency, record_path=str(tmp_path / "paper.jsonl"), keywords=keywords)

    def on_alert(alert: Alert) -> None:
        trader.on_alert(alert)
        alerts.append(alert)

    engine = LiveEngine(None, cfg, scoring, on_alert, on_evaluate=trader.on_evaluate, keep_alive=trader.keep_alive)
    trader.attach(engine)
    return engine, trader, alerts


def run_ticks(engine: LiveEngine, trader: PaperTrader, start: float, end: float, step: float = 1.0) -> None:
    t = start
    while t <= end:
        trader.on_tick(t)
        engine.tick(t)
        t += step


def test_entries_exits_paths_and_report(tmp_path):
    engine, trader, alerts = make_paper_engine(tmp_path)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    m58 = b58encode(mint)
    # organic start: 14 buyers 1.2 s apart -> GO around 25 s
    feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12)
    run_ticks(engine, trader, T0 + 4, T0 + 28)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]  # evaluated every second, BLICK comes first
    go_at = alerts[-1].state.tiers_sent["GO"]
    blick_at = alerts[-1].state.tiers_sent["BLICK"]
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    buys = {r["strategie"]: r for r in recs if r["typ"] == "kauf"}
    # every GO strategy bought, two seconds after the alert, on the curve price of that moment
    for name in ("GO-3x", "GO-2x", "GO-trail", "GO-halb", "GO-bis-RUG", "DEV-HÄLT"):
        assert name in buys, name
        assert abs(buys[name]["t"] - (go_at + 2.0)) < 1.01 and buys[name]["latenz_s"] >= 2.0
        assert buys[name]["sol_in"] == 0.08 and buys[name]["kontext"]["wort"] == "GO" and buys[name]["kontext"]["dev_verkauft"] == 0
    # the clean early strategy entered before the alert, once three outside buyers were there
    assert "SAUBER-früh" in buys and buys["SAUBER-früh"]["t"] < go_at and buys["SAUBER-früh"]["kontext"]["wort"] == "FRÜH"
    # narrative 55 (trend word missing, no socials): the narrative strategies stay out
    assert "NARRATIV-GO" not in buys and "NARRATIV-früh" not in buys
    assert "BLICK-3x" in buys and abs(buys["BLICK-3x"]["t"] - (blick_at + 2.0)) < 1.01 and buys["BLICK-3x"]["t"] < buys["GO-3x"]["t"]
    entry = buys["GO-3x"]["preis"]
    # a 3x: big buys with tiny token amounts push the curve price up (the helper curve is not constant product)
    for i in range(30):
        engine.on_logs(m58, 9600 + i, f"pump{i}", None, trade_logs(mint, key(), 2.5, 1_000_000.0, True, int(T0 + 40 + i), creator), now=T0 + 40 + i)
        trader.on_tick(T0 + 40 + i)
        engine.tick(T0 + 40 + i)
    run_ticks(engine, trader, T0 + 71, T0 + 76)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    sells = [r for r in recs if r["typ"] == "verkauf"]
    by = {(r["strategie"], r["grund"].split(" ")[0]) for r in sells}
    assert ("GO-3x", "TP") in by and ("GO-2x", "TP") in by and ("GO-schnell", "TP") in by and ("SAUBER-früh", "TP") in by
    assert ("GO-halb", "TEIL") in by  # half sold at 2x, the rest rides
    tp = next(r for r in sells if r["strategie"] == "GO-3x")
    assert tp["abgeschlossen"] and tp["pnl_pct"] > 150 and tp["kurs"] / entry >= 2.9 and tp["hoch"] >= 3.0
    assert ("GO-bis-RUG", "TP") not in by and ("GO-bis-RUG", "ZEIT") not in by  # still holding
    # the crash: sellers dump, price falls below the trailing stop and the rug rules -> RUG for the holders
    for i in range(12):
        engine.on_logs(m58, 9700 + i, f"dump{i}", None, trade_logs(mint, key(), 6.0, 1_000_000.0, False, int(T0 + 80 + i), creator), now=T0 + 80 + i)
        trader.on_tick(T0 + 80 + i)
        engine.tick(T0 + 80 + i)
    run_ticks(engine, trader, T0 + 93, T0 + 100)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    sells = [r for r in recs if r["typ"] == "verkauf"]
    reasons = {r["strategie"]: r["grund"].split(" ")[0] for r in sells if r["abgeschlossen"]}
    assert reasons["GO-trail"] == "TRAIL" or reasons["GO-trail"] == "RUG"
    assert reasons["GO-bis-RUG"] in ("RUG", "SL") and reasons["GO-halb"] in ("TRAIL", "RUG")
    assert trader.stats["offen"] == 0
    # the token stays subscribed while the paper trader still wants it, then the path is written and it expires
    assert m58 in engine.tokens
    run_ticks(engine, trader, T0 + 101, T0 + 1000, step=5.0)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    paths = [r for r in recs if r["typ"] == "pfad"]
    assert len(paths) == 1 and paths[0]["mint"] == m58 and paths[0]["schritt"] == 5 and len(paths[0]["punkte"]) >= 150
    assert max(p[1] for p in paths[0]["punkte"]) >= 3 * entry and m58 not in engine.tokens
    text = paper_report(recs, cash=0.25)
    assert "GO-3x" in text and "Papier-Trades" in text and ("Kandidat" in text or "Noch keine Strategie" in text)
    # every record line is valid JSON with the fields a reader needs
    for r in recs:
        assert r["typ"] in ("kauf", "verkauf", "pfad", "skip") and "t" in r or r["typ"] == "pfad"


def test_rug_alert_before_execution_cancels_the_order_and_dev_sale_exit(tmp_path):
    engine, trader, alerts = make_paper_engine(tmp_path, strategies=strategies_by_name(["GO-3x", "DEV-HÄLT", "GO-bis-RUG"]))
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator, initial_buy_tokens=50_000_000.0, sol=1.5), now=T0)
    CURVES[mint] = [31_500_000_000, 1_073_000_000_000_000 - 50_000_000_000_000]
    m58 = b58encode(mint)
    feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12)
    run_ticks(engine, trader, T0 + 4, T0 + 30)
    assert [a.tier for a in alerts] == ["BLICK", "GO"] and trader.stats["kauf"] == 3
    # the dev sells 40 %: DEV-HÄLT and GO-bis-RUG leave, GO-3x stays
    engine.on_logs(m58, 9800, "devsell", None, trade_logs(mint, creator, 0.6, 20_000_000.0, False, int(T0 + 35), creator), now=T0 + 35)
    run_ticks(engine, trader, T0 + 35, T0 + 40)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    reasons = {r["strategie"]: r["grund"] for r in recs if r["typ"] == "verkauf"}
    assert reasons.get("DEV-HÄLT") == "DEV-RAUS" and reasons.get("GO-bis-RUG") == "DEV-RAUS" and "GO-3x" not in reasons


def test_time_exit_keeps_a_dead_token_subscribed_until_the_position_closes(tmp_path):
    from holder_scorer.paper import Strategy

    hold = Strategy("ZEIT-test", "GO", tp=None, sl=None, max_hold_s=180.0, exit_on_rug=False)
    engine, trader, alerts = make_paper_engine(tmp_path, strategies=[hold])
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    m58 = b58encode(mint)
    feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12)
    run_ticks(engine, trader, T0 + 4, T0 + 30)
    assert trader.stats["kauf"] == 1
    # trading stops: the engine calls it TOT (and RUG-alerts) but keeps the token because a paper position is open
    run_ticks(engine, trader, T0 + 31, T0 + 150)
    assert "RUG" in [a.tier for a in alerts] and m58 in engine.tokens and trader.stats["offen"] == 1
    run_ticks(engine, trader, T0 + 151, T0 + 240)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    sell = next(r for r in recs if r["typ"] == "verkauf")
    assert sell["grund"].startswith("ZEIT 3 min") and 180 <= sell["dauer_s"] <= 185
    assert -4 < sell["pnl_pct"] < 0  # flat price: the round trip costs the two fees and the impact
    run_ticks(engine, trader, T0 + 241, T0 + 1200, step=5.0)
    assert m58 not in engine.tokens and trader.stats["pfade"] == 1


def test_narrative_score_and_copycats():
    score, reasons = narrative_score("Live Coin", "LIVE", None, 0, False, ["live"])
    assert score == 55 and "Trend: live" in reasons
    score2, reasons2 = narrative_score("Live Coin", "LIVE", {"description": "A long description of the story behind this coin, really.", "image": "x"}, 3, False, ["live"])
    assert score2 == 100
    score3, reasons3 = narrative_score("test123", "T", None, 0, True, [])
    assert score3 == 0 and "Wegwerf-Name" in reasons3 and "KOPIE" in reasons3
    reg = NameRegistry()
    reg.register("m1", "Pepe Reloaded", "PEPER", T0)
    assert reg.is_copycat("m2", "PEPE RELOADED!", "X", T0 + 60)
    assert reg.is_copycat("m3", "Other", "peper", T0 + 60)
    assert not reg.is_copycat("m1", "Pepe Reloaded", "PEPER", T0 + 60)  # its own entry
    assert not reg.is_copycat("m4", "Pepe Reloaded", "PEPER", T0 + 7200)  # window passed


def test_narrative_strategy_enters_with_socials(tmp_path):
    engine, trader, alerts = make_paper_engine(tmp_path, strategies=strategies_by_name(["NARRATIV-früh", "NARRATIV-GO"]), keywords=["live"])
    mint, creator = key(), key()
    state = engine.on_launch(launch_msg(mint, creator), now=T0)
    state.metadata = {"twitter": "https://x.com/a/status/1", "telegram": "https://t.me/abc/1", "website": "https://example.com/page", "description": "x" * 50, "image": "i"}
    state.metadata_ok = True
    feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12)
    run_ticks(engine, trader, T0 + 4, T0 + 30)
    recs = load_paper(str(tmp_path / "paper.jsonl"))
    buys = {r["strategie"]: r for r in recs if r["typ"] == "kauf"}
    assert "NARRATIV-früh" in buys and "NARRATIV-GO" in buys
    assert buys["NARRATIV-früh"]["kontext"]["narrativ"] >= 60 and "Narrativ" in buys["NARRATIV-früh"]["ausloeser"]
    assert buys["NARRATIV-früh"]["t"] < buys["NARRATIV-GO"]["t"]


def test_simulate_rule_on_a_path_and_strategy_lookup():
    path = {"start": 0.0, "schritt": 5.0, "punkte": [[1.0, 1.1, 0.9], [1.5, 2.1, 1.4], [1.2, 1.3, 0.5], [1.0, 1.0, 1.0]]}
    fee = 1 - CURVE_FEE_BPS / 10_000
    assert simulate_rule(path, 0.0, 1.0, 2.0, 0.4, 600.0) == (2.0 * fee - 1.0, "TP")
    assert simulate_rule(path, 0.0, 1.0, 3.0, 0.4, 600.0) == ((1 - 0.4) * fee - 1.0, "SL")
    assert simulate_rule(path, 0.0, 1.0, 3.0, None, 10.0)[1] == "ZEIT"
    assert simulate_rule(path, 100.0, 1.0, 3.0, None, 10.0) is None
    assert [s.name for s in strategies_by_name(["go-3x", "BLICK-trail"])] == ["GO-3x", "BLICK-trail"]
    try:
        strategies_by_name(["gibtsnicht"])
    except ValueError as exc:
        assert "unbekannte" in str(exc)
    else:
        raise AssertionError("unknown strategy accepted")


class HistoryRpc:
    def __init__(self, mint58: str, sigs: list[dict], txs: dict):
        self.mint = mint58
        self.sigs = sigs
        self.txs = txs
        self.stats = {"requests": 0, "posts": 0, "retries": 0, "by_method": {}}

    def get_signatures(self, address, limit=1000, before=None):
        assert address == self.mint
        return list(self.sigs) if before is None else []

    def get_transactions(self, signatures):
        return {s: self.txs.get(s) for s in signatures}


def test_look_back_recomputes_past_calls_from_chain_history(tmp_path):
    mint, creator = key(), key()
    m58 = b58encode(mint)
    t_call = 1_800_000_000
    vsol, vtok = 33_000_000_000, 1_000_000_000_000_000
    sigs, txs = [], {}
    # price path after the call: flat, then 3x at +60 s, then a collapse at +200 s
    plan = [(-30, 0.1), (3, 0.1), (20, 0.1), (60, 80.0), (200, -80.0), (400, 0.05)]
    for i, (dt, sol) in enumerate(plan):
        lam = int(abs(sol) * 1e9)
        raw = 1_000_000_000 if sol > 0 else 1_000_000_000
        if sol > 0:
            vsol, vtok = vsol + lam, vtok - raw
        else:
            vsol, vtok = vsol - lam, vtok + raw
        ts = t_call + dt
        payer = key()
        ev = TRADE_EVENT_DISC + trade_event_bytes(mint, payer, lam, raw, sol > 0, ts, creator, reserves=(vsol, vtok))
        sig = f"s{i}"
        sigs.append({"signature": sig, "slot": 100 + i, "blockTime": ts, "err": None})
        txs[sig] = fake_tx(sig, 100 + i, ts, payer, [ev])
    sigs.reverse()  # newest first, like the RPC
    rpc = HistoryRpc(m58, sigs, txs)
    text = look_back(rpc, [(m58, float(t_call))], size_sol=0.08, latency_s=2.0, horizon_s=900.0)
    assert "Hoch danach" in text and "erreichen 3x" in text
    assert "TP 3x / SL −40 % / 10 min → +196 %" in text  # 3x minus the sell fee, hit before the collapse
    calls_file = tmp_path / "calls.txt"
    calls_file.write_text(f"# alte Calls\n{m58} {t_call}\n{m58} 2026-09-26T18:30:00Z\n", encoding="utf-8")
    calls = parse_calls_file(str(calls_file))
    assert len(calls) == 2 and calls[0] == (m58, float(t_call)) and abs(calls[1][1] - 1_790_447_400) < 86400 * 3


def test_report_on_an_empty_or_partial_file(tmp_path):
    f = tmp_path / "p.jsonl"
    f.write_text(json.dumps({"typ": "kauf", "t": T0, "strategie": "GO-3x", "mint": "m", "preis": 1.0, "sol_in": 0.08}) + "\n", encoding="utf-8")
    text = paper_report(load_paper(str(f)))
    assert "Noch keine abgeschlossenen" in text and "1 Käufe" in text
