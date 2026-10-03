"""Edge-Lab-Fixes vom 2026-09-29: WIDERRUF-Alarm, Tape, vollständige Alarm-Records, Telegram-Queue, Papier-Look-ahead."""
from __future__ import annotations

import json

from holder_scorer.encoding import b58encode
from holder_scorer.calibrate import alert_record_extra, rules_hash
from holder_scorer.live import LiveConfig
from holder_scorer.notify import TelegramSender
from holder_scorer.pump import BondingCurveState
from holder_scorer import paper
from tests.helpers import key
from tests.test_live import T0, feed_buyers, launch_msg, make_engine, trade_logs


def _blick(engine, mint, creator):
    engine.on_launch(launch_msg(mint, creator), now=T0)
    engine.on_logs(b58encode(mint), 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.5, sol=0.12)
    engine.tick(T0 + 12)


def test_widerruf_after_blick_when_a_soft_veto_appears():
    engine, alerts = make_engine(stufe=2, tiers=("BLICK", "GO", "WIDERRUF", "RUG"))
    mint, creator = key(), key()
    _blick(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK"]
    # the dev buys another 10 % of the supply: DEV-GROSS is a soft veto (blocks GO, is not a rug pattern)
    engine.on_logs(b58encode(mint), 5100, "devbuy", None, trade_logs(mint, creator, 3.0, 100_000_000.0, True, int(T0 + 14), creator), now=T0 + 14)
    engine.tick(T0 + 15)
    tiers = [a.tier for a in alerts]
    assert tiers == ["BLICK", "WIDERRUF"], (tiers, engine.evaluate(engine.tokens[b58encode(mint)], T0 + 15).flags)
    assert alerts[1].report.word == "WIDERRUF" and alerts[1].text.startswith("↩️ WIDERRUF")
    assert "nach BLICK" in alerts[1].text.splitlines()[0] and "DEV-GROSS" in alerts[1].text
    # sent once only
    engine.tick(T0 + 20)
    assert [a.tier for a in alerts] == ["BLICK", "WIDERRUF"]


def test_widerruf_not_sent_without_tier_or_after_go():
    engine, alerts = make_engine(stufe=2, tiers=("BLICK", "GO", "RUG"))
    mint, creator = key(), key()
    _blick(engine, mint, creator)
    engine.on_logs(b58encode(mint), 5100, "devbuy", None, trade_logs(mint, creator, 3.0, 100_000_000.0, True, int(T0 + 14), creator), now=T0 + 14)
    engine.tick(T0 + 15)
    assert [a.tier for a in alerts] == ["BLICK"]


def test_tape_backfills_at_first_alert_and_streams_afterwards(tmp_path):
    engine, alerts = make_engine(stufe=2, tiers=("BLICK", "GO", "WIDERRUF", "RUG"))
    engine.cfg.tape_path = str(tmp_path / "tape.jsonl")
    mint, creator = key(), key()
    _blick(engine, mint, creator)
    state = engine.tokens[b58encode(mint)]
    rows = [json.loads(line) for line in (tmp_path / "tape.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(state.trades) and all(r["backfill"] for r in rows)
    assert {r["mint"] for r in rows} == {b58encode(mint)}
    assert set(rows[0]) >= {"slot", "ts", "sig", "buy", "user", "sol", "tok", "vS", "vT", "rS", "rT", "fee"}
    feed_buyers(engine, mint, creator, 2, T0 + 20, 1.0, slot0=5200)
    rows = [json.loads(line) for line in (tmp_path / "tape.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(state.trades) and sum(1 for r in rows if not r["backfill"]) == 2
    # tokens without an alert are not taped
    other, creator2 = key(), key()
    engine.on_launch(launch_msg(other, creator2), now=T0 + 30)
    feed_buyers(engine, other, creator2, 2, T0 + 31, 1.0, slot0=6000)
    rows = [json.loads(line) for line in (tmp_path / "tape.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["mint"] for r in rows} == {b58encode(mint)}


def test_alert_record_extra_carries_slot_curve_and_rule_version():
    engine, alerts = make_engine(stufe=2, tiers=("BLICK", "GO", "WIDERRUF", "RUG"))
    mint, creator = key(), key()
    _blick(engine, mint, creator)
    cfg, scoring = LiveConfig.for_stufe(2)
    rules = rules_hash(cfg, scoring, "0.3.1")
    assert len(rules) == 12 and rules == rules_hash(cfg, scoring, "0.3.1")
    scoring.yes_threshold += 1
    assert rules != rules_hash(cfg, scoring, "0.3.1")
    extra = alert_record_extra(alerts[0], 2, rules, "0.3.1", cfg, scoring)
    assert extra["tier"] == "BLICK" and extra["rules_hash"] == rules and extra["version"] == "0.3.1"
    assert extra["slot"] > 0 and extra["curve"]["virtual_token_reserves"] > 0 and extra["creator"] == b58encode(creator)
    assert extra["trades_seen"] == len(alerts[0].state.trades) and extra["create_slot_known"] is False
    json.dumps(extra)  # must be serialisable as one JSONL line


def test_telegram_sender_retries_on_429_and_keeps_order():
    calls: list[str] = []
    attempts = {"n": 0}

    def fake_send(text):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return False, 0.01, "http 429 Too Many Requests"
        calls.append(text)
        return True, None, ""

    sender = TelegramSender(max_retries=3, min_interval_s=0.0, send=fake_send)
    sender.send("GO")
    sender.send("RUG")
    sender.close()
    assert calls == ["GO", "RUG"]
    assert (sender.sent, sender.retries, sender.failed) == (2, 1, 0)


def test_telegram_sender_counts_lost_messages():
    sender = TelegramSender(max_retries=1, min_interval_s=0.0, send=lambda text: (False, None, "ConnectionError"))
    sender.send("GO")
    sender.close()
    assert (sender.sent, sender.retries, sender.failed) == (0, 1, 1)
    assert "ConnectionError" in sender.status_line()


def test_simulate_rule_ignores_prices_before_the_entry_in_its_first_bucket():
    path = {"schritt": 5.0, "start": 0.0, "punkte": [(1.0, 1.2, 0.5), (1.1, 1.15, 1.05)]}
    res = paper.simulate_rule(path, t_entry=4.9, entry_price=1.0, tp=None, sl=0.4, hold_s=60.0)
    assert res is not None and res[1] == "ZEIT"  # the 0.5 low happened before the entry and must not trigger the stop
    fee = 1.0 - paper.CURVE_FEE_BPS / 10_000
    assert abs(res[0] - (1.1 * fee - 1.0)) < 1e-9


def _curve(v_sol: int, v_tok: int) -> BondingCurveState:
    return BondingCurveState(
        virtual_token_reserves=v_tok,
        virtual_quote_reserves=v_sol,
        real_token_reserves=793_100_000_000_000 - (1_073_000_000_000_000 - v_tok),
        real_quote_reserves=v_sol - 30_000_000_000,
        token_total_supply=1_000_000_000_000_000,
        complete=False,
        creator=None,
        quote_mint=None,
        is_mayhem_mode=False,
    )


def test_look_back_enters_on_the_curve_as_it_stood_at_call_plus_latency(monkeypatch):
    t_call = 1_800_000_000.0
    before = _curve(31_000_000_000, 1_038_387_096_774_193)  # state after ~1 SOL of buys
    after = _curve(41_000_000_000, 785_121_951_219_512)  # a big buy one second after our (hypothetical) entry
    trades = [(t_call - 5.0, paper.curve_price(before), before), (t_call + 3.0, paper.curve_price(after), after)]
    monkeypatch.setattr(paper, "fetch_trade_path", lambda rpc, mint, t0, t1: trades)
    text = paper.look_back(None, [("M" * 44, t_call)], size_sol=0.08, latency_s=2.0, horizon_s=60.0)
    tokens, _, _ = paper.buy_on_curve(before, int(0.08 * paper.LAMPORTS_PER_SOL))
    entry_price = 0.08 / (tokens / paper.RAW_PER_TOKEN)
    assert f"bei MC {entry_price * paper.SUPPLY_TOKENS:.0f} SOL" in text  # priced on `before`, not on the later trade
