"""Live engine: launches from PumpPortal frames, trades from log notifications, alert tiers."""
from __future__ import annotations

import base64

from holder_scorer.collect import CreatorHistory
from holder_scorer.encoding import b58encode
from holder_scorer.live import (
    CREATE_B64_PREFIX,
    TRADE_B64_PREFIX,
    Alert,
    LiveConfig,
    LiveEngine,
    SolanaLogStream,
    parse_log_events,
    ws_url_from_rpc,
)
from holder_scorer.pump import CREATE_EVENT_DISC, TRADE_EVENT_DISC
from holder_scorer.scoring import ScoringConfig  # noqa: F401 - re-exported for probes
from tests.helpers import create_event_bytes, key, trade_event_bytes

T0 = 1_800_000_000.0
PUMP_LOG = "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]"


def launch_msg(mint: bytes, creator: bytes, initial_buy_tokens: float = 20_000_000.0, sol: float = 0.5):
    return {
        "signature": "createsig",
        "mint": b58encode(mint),
        "traderPublicKey": b58encode(creator),
        "txType": "create",
        "initialBuy": initial_buy_tokens,
        "solAmount": sol,
        "bondingCurveKey": b58encode(key()),
        "vTokensInBondingCurve": 1_073_000_000.0 - initial_buy_tokens,
        "vSolInBondingCurve": 30.0 + sol,
        "marketCapSol": 28.9,
        "name": "Live Coin",
        "symbol": "LIVE",
        "uri": "",
        "pool": "pump",
    }


CURVES: dict[bytes, list[int]] = {}  # mint -> [virtual SOL lamports, virtual token raw units], cumulative like the real curve


def trade_logs(mint: bytes, user: bytes, sol: float, tokens: float, is_buy: bool, ts: int, creator: bytes) -> list[str]:
    curve = CURVES.setdefault(mint, [30_500_000_000, 1_073_000_000_000_000 - 20_000_000_000_000])
    lamports, raw = int(sol * 1e9), int(tokens * 1e6)
    if is_buy:
        curve[0] += lamports
        curve[1] -= raw
    else:
        curve[0] -= lamports
        curve[1] += raw
    body = trade_event_bytes(mint, user, lamports, raw, is_buy, ts, creator, reserves=(curve[0], curve[1]))
    return [PUMP_LOG, "Program log: Instruction: Buy" if is_buy else "Program log: Instruction: Sell", "Program data: " + base64.b64encode(TRADE_EVENT_DISC + body).decode(), "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success"]


def make_engine(stufe: int = 2, tiers=("BLICK", "GO", "RUG"), side=None):
    alerts: list[Alert] = []
    cfg, scoring = LiveConfig.for_stufe(stufe)
    cfg.tiers = tiers
    engine = LiveEngine(None, cfg, scoring, alerts.append, run_side_task=side)
    return engine, alerts


def test_log_prefixes_and_parser():
    mint, user, creator = key(), key(), key()
    trade = TRADE_EVENT_DISC + trade_event_bytes(mint, user, 10**8, 10**12, True, 5, creator)
    create = CREATE_EVENT_DISC + create_event_bytes("n", "s", "u", mint, key(), creator, creator, 5)
    t_line = "Program data: " + base64.b64encode(trade).decode()
    c_line = "Program data: " + base64.b64encode(create).decode()
    assert t_line[len("Program data: ") :].startswith(TRADE_B64_PREFIX)
    assert c_line[len("Program data: ") :].startswith(CREATE_B64_PREFIX)
    trades, creates, completed = parse_log_events([PUMP_LOG, t_line, c_line, "Program data: !!!notbase64", "Program log: x"])
    assert len(trades) == 1 and trades[0].user == b58encode(user)
    assert len(creates) == 1 and creates[0].name == "n" and not completed
    # an event emitted by another program inside the same transaction is ignored
    other = ["Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 invoke [1]", t_line, "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 success", PUMP_LOG, c_line, "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success"]
    trades2, creates2, _ = parse_log_events(other)
    assert trades2 == [] and len(creates2) == 1
    # pump.fun's own self-CPI frame still counts as pump.fun
    nested = [PUMP_LOG, "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [2]", "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success", t_line, "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success"]
    assert len(parse_log_events(nested)[0]) == 1
    assert ws_url_from_rpc("https://mainnet.helius-rpc.com/?api-key=k") == "wss://mainnet.helius-rpc.com/?api-key=k"


def test_launch_creates_state_with_dev_buy():
    engine, alerts = make_engine()
    mint, creator = key(), key()
    state = engine.on_launch(launch_msg(mint, creator), now=T0)
    assert state is not None and state.creator == b58encode(creator)
    assert len(state.trades) == 1 and state.trades[0].user == b58encode(creator) and state.trades[0].sol_amount == 500_000_000
    assert state.curve is not None and state.curve.virtual_quote_reserves == 30_500_000_000
    assert engine.on_launch(launch_msg(mint, creator), now=T0) is None  # duplicate
    assert engine.on_launch({"mint": b58encode(key()), "pool": "bonk", "txType": "create"}, now=T0) is None


def feed_buyers(engine: LiveEngine, mint: bytes, creator: bytes, n: int, start: float, gap: float, sol: float = 0.08, slot0: int = 5000) -> list[bytes]:
    buyers = []
    for i in range(n):
        buyer = key()
        buyers.append(buyer)
        t = start + i * gap
        slot = slot0 + int((t - start) / 0.25) + 3
        engine.on_logs(b58encode(mint), slot, f"sig{start}-{i}", None, trade_logs(mint, buyer, sol, 800_000.0, True, int(t), creator), now=t)
    return buyers


def test_blick_then_go_then_rug():
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    # first real buyer inside the creation window defines slot 0
    engine.on_logs(b58encode(mint), 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
    state = engine.tokens[b58encode(mint)]
    assert state.create.slot == 5000 and state.trades[0].slot == 5000
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.5, sol=0.12)  # 0.72 SOL organic inflow
    engine.tick(T0 + 12)
    tiers = [a.tier for a in alerts]
    assert tiers == ["BLICK"], (tiers, engine.evaluate(state, T0 + 12).to_dict()["flags"], engine.evaluate(state, T0 + 12).verdict.features.organic_net_flow_120s_sol)
    assert alerts[0].report.word == "BLICK" and alerts[0].text.startswith("👀 BLICK")
    assert alerts[0].text.splitlines()[-1] == f"pump.fun/coin/{b58encode(mint)}"
    # more buyers: the scorer's own gates are met at ~25 s
    feed_buyers(engine, mint, creator, 10, T0 + 14, 1.0)
    engine.tick(T0 + 26)
    tiers = [a.tier for a in alerts]
    assert tiers == ["BLICK", "GO"], tiers
    assert "nach BLICK" in alerts[1].text.splitlines()[0]
    assert engine.stats["go"] == 1
    # the dev dumps everything: RUG update, token final
    engine.on_logs(b58encode(mint), 5400, "devsell", None, trade_logs(mint, creator, 0.6, 20_000_000.0, False, int(T0 + 40), creator), now=T0 + 40)
    engine.tick(T0 + 41)
    tiers = [a.tier for a in alerts]
    assert tiers == ["BLICK", "GO", "RUG"], tiers
    assert "DEV-DUMP" in alerts[2].text and "nach GO" in alerts[2].text
    assert state.final
    # linger, then expire and unsubscribe
    assert engine.tick(T0 + 41 + 5) == []
    assert engine.tick(T0 + 41 + 31) == [b58encode(mint)]
    assert b58encode(mint) not in engine.tokens


def test_no_blick_with_bundle_or_serial_creator():
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    # six wallets buy 6 % each in the creation block
    for i in range(6):
        engine.on_logs(b58encode(mint), 7000, f"bundle{i}", None, trade_logs(mint, key(), 1.0, 60_000_000.0, True, int(T0), creator), now=T0 + 0.3)
    feed_buyers(engine, mint, creator, 8, T0 + 3, 1.0, slot0=7000)
    engine.tick(T0 + 12)
    assert [a.tier for a in alerts] == []
    state = engine.tokens[b58encode(mint)]
    assert state.last_word == "RUG"

    engine2, alerts2 = make_engine(stufe=2)
    mint2, creator2 = key(), key()
    engine2.on_launch(launch_msg(mint2, creator2), now=T0)
    st2 = engine2.tokens[b58encode(mint2)]
    st2.creator_history = CreatorHistory(address=b58encode(creator2), prior_tokens=9, graduated=0, dead=8, source="rpc")
    st2.done.add("creator")
    feed_buyers(engine2, mint2, creator2, 8, T0 + 3, 1.0)
    engine2.tick(T0 + 12)
    assert [a.tier for a in alerts2] == []
    assert any(f.startswith("SERIE") for f in engine2.evaluate(st2, T0 + 13).flags)


def test_stufe_presets_change_thresholds():
    c1, s1 = LiveConfig.for_stufe(1)
    c3, s3 = LiveConfig.for_stufe(3)
    assert c1.blick_min_outside_buyers > LiveConfig.for_stufe(2)[0].blick_min_outside_buyers > c3.blick_min_outside_buyers
    assert s1.min_age_s == 90 and s3.min_age_s == 15 and s3.yes_min_outside_buyers == 4 and s3.yes_threshold == 55
    engine, alerts = make_engine(stufe=3)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    # first buyer inside the 1.5 s window: exact creation slot, so nothing is held back by the guessed-window grace
    feed_buyers(engine, mint, creator, 5, T0 + 1, 1.0, sol=0.1)
    engine.tick(T0 + 7)
    assert [a.tier for a in alerts] == ["BLICK"]
    # the same start would still be too little for stufe 1 (8 buyers, 1 SOL)
    engine1, alerts1 = make_engine(stufe=1)
    mint1, creator1 = key(), key()
    engine1.on_launch(launch_msg(mint1, creator1), now=T0)
    feed_buyers(engine1, mint1, creator1, 5, T0 + 1, 1.0, sol=0.1)
    engine1.tick(T0 + 7)
    assert alerts1 == []


def test_missing_event_fallback_and_side_tasks():
    calls = []

    def side(name, fn, done, delay=0.0, group="rpc"):
        calls.append(name)
        if name == "creator":
            done((CreatorHistory(address="c", prior_tokens=1, graduated=1, source="rpc"), None, None))
        else:
            done(None)

    engine, alerts = make_engine(stufe=2, side=side)
    engine.rpc = object()  # side tasks are only scheduled when an rpc exists (no stats attribute: budget always ok)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    assert calls == []  # nothing at launch: metadata needs a uri, the create tx waits for the first outside buyer
    # a log without a decodable event is queued for a getTransaction fallback
    engine.on_logs(b58encode(mint), 6000, "cpi-only", None, [PUMP_LOG, "Program log: Instruction: Buy"], now=T0 + 2)
    assert engine.take_missing() == ["cpi-only"] and engine.take_missing() == []
    # a truncated log is fetched even though it carried a decodable event
    engine.on_logs(b58encode(mint), 6001, "cut", None, trade_logs(mint, key(), 0.05, 400_000.0, True, int(T0 + 2), creator) + ["Log truncated"], now=T0 + 2.5)
    assert engine.take_missing() == ["cut"]
    from tests.helpers import fake_tx

    payer = key()
    tx = fake_tx("cpi-only", 6000, int(T0 + 2), payer, [TRADE_EVENT_DISC + trade_event_bytes(mint, payer, 10**8, 10**12, True, int(T0 + 2), creator)])
    assert engine.apply_fetched_transactions({"cpi-only": tx}, now=T0 + 3) == 1
    assert engine.apply_fetched_transactions({"cpi-only": tx}, now=T0 + 3) == 0  # deduplicated
    # the late "cut" trade at slot 6001 put the guessed creation slot at 5996: these buyers must land after that window
    feed_buyers(engine, mint, creator, 5, T0 + 4, 1.0, slot0=6002)
    engine.tick(T0 + 10)
    assert "create_tx" in calls and "creator" in calls and "profiles" in calls
    state = engine.tokens[b58encode(mint)]
    assert state.creator_history is not None and state.creator_history.prior_tokens == 1


def test_create_slot_uses_earliest_window_trade_and_own_create_log():
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    state = engine.tokens[b58encode(mint)]
    # three trades inside the creation window at slots 5000, 5003, 5005: slot 0 must be 5000, not 5005
    engine.on_logs(b58encode(mint), 5003, "w1", None, trade_logs(mint, key(), 0.3, 3_000_000.0, True, int(T0), creator), now=T0 + 0.3)
    engine.on_logs(b58encode(mint), 5000, "w0", None, trade_logs(mint, key(), 0.3, 3_000_000.0, True, int(T0), creator), now=T0 + 0.9)
    engine.on_logs(b58encode(mint), 5005, "w2", None, trade_logs(mint, key(), 0.3, 3_000_000.0, True, int(T0), creator), now=T0 + 1.4)
    assert state.create.slot == 5000 and state.trades[0].slot == 5000 and state.trades[0].user == b58encode(creator)
    # the create transaction's own log notification is not discarded: it carries the exact slot and dev buy
    dev_logs = trade_logs(mint, creator, 0.5, 20_000_000.0, True, int(T0), creator)
    dev_logs.insert(2, "Program data: " + base64.b64encode(CREATE_EVENT_DISC + create_event_bytes("Live Coin", "LIVE", "ipfs://meta", mint, key(), creator, creator, int(T0))).decode())
    assert engine.on_logs(b58encode(mint), 4999, "createsig", None, dev_logs, now=T0 + 1.6) == 1
    assert state.create_slot_known and state.create.slot == 4999 and state.create.uri == "ipfs://meta"
    dev_trades = [t for t in state.trades if t.user == b58encode(creator)]
    assert len(dev_trades) == 1 and dev_trades[0].slot == 4999 and dev_trades[0].ix_name == "buy"
    feats = engine.evaluate(state, T0 + 20).verdict.features
    # with the real create slot 4999 the window ends at 5003: the slot-5005 buyer is organic, not bundle
    assert feats.creation_slot_buyers == 2 and feats.dev_buy_share == 0.02


def test_blick_respects_stufe_bundle_limit_and_not_with_go():
    engine, alerts = make_engine(stufe=3)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    # a 3 % creation-window share: vetoed at stufe 1 (5 %)? no, allowed there too; vetoed only above the stufe limit
    engine.on_logs(b58encode(mint), 8000, "b0", None, trade_logs(mint, key(), 1.0, 30_000_000.0, True, int(T0), creator), now=T0 + 0.5)
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.0, sol=0.1, slot0=8000)
    engine.tick(T0 + 10)
    assert [a.tier for a in alerts] == ["BLICK"]
    limits = [LiveConfig.for_stufe(s)[0].max_bundle_share for s in (1, 2, 3)]
    assert limits[0] < limits[1] < limits[2] and 0.03 < limits[2]
    # a delayed first evaluation that already satisfies GO must not also send BLICK
    engine2, alerts2 = make_engine(stufe=2)
    mint2, creator2 = key(), key()
    engine2.on_launch(launch_msg(mint2, creator2), now=T0)
    feed_buyers(engine2, mint2, creator2, 16, T0 + 3, 1.2, sol=0.12)
    engine2.tick(T0 + 30)
    assert [a.tier for a in alerts2] == ["GO"]


def test_alert_callback_failure_is_retried_then_given_up():
    attempts = {"n": 0}

    def flaky(alert):
        attempts["n"] += 1
        raise RuntimeError("telegram down")

    cfg, scoring = LiveConfig.for_stufe(1)  # no GO before 90 s, so only BLICK is attempted here
    cfg.tiers = ("BLICK",)
    engine = LiveEngine(None, cfg, scoring, flaky)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    feed_buyers(engine, mint, creator, 9, T0 + 3, 1.0, sol=0.15)
    state = engine.tokens[b58encode(mint)]
    for i in range(5):
        engine.tick(T0 + 13 + i * 6)
    assert attempts["n"] == cfg.max_alert_retries and "BLICK" in state.tiers_sent


def test_go_is_gated_and_bundle_exit_triggers_rug_after_go():
    # a 17 % creation-block bundle plus real followers: no GO at any stufe (limit 15 % on stufe 3)
    for stufe in (1, 2, 3):
        engine, alerts = make_engine(stufe=stufe)
        mint, creator = key(), key()
        engine.on_launch(launch_msg(mint, creator), now=T0)
        for i in range(4):
            engine.on_logs(b58encode(mint), 9000, f"bundle{i}", None, trade_logs(mint, key(), 1.3, 42_500_000.0, True, int(T0), creator), now=T0 + 0.3)
        feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12, slot0=9000)
        engine.tick(T0 + 25)
        engine.tick(T0 + 95)
        assert "GO" not in [a.tier for a in alerts], (stufe, [a.tier for a in alerts])
    # a small (4 %) bundle is tolerated for GO on stufe 2, but when it dumps after GO the user gets a RUG
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    ring = [key() for _ in range(2)]
    for i, w in enumerate(ring):
        engine.on_logs(b58encode(mint), 9100, f"b{i}", None, trade_logs(mint, w, 0.6, 20_000_000.0, True, int(T0), creator), now=T0 + 0.3)
    feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12, slot0=9100)
    engine.tick(T0 + 25)
    assert [a.tier for a in alerts] == ["GO"]
    for i, w in enumerate(ring):
        engine.on_logs(b58encode(mint), 9300 + i, f"s{i}", None, trade_logs(mint, w, 0.5, 20_000_000.0, False, int(T0 + 30), creator), now=T0 + 30)
    engine.tick(T0 + 31)
    assert [a.tier for a in alerts] == ["GO", "RUG"]
    # the ring is both the bundle and the first buyers: either exit rule may fire first
    fails = " ".join(alerts[1].report.verdict.hard_fails)
    assert "Bundle" in fails or "Erstkäufer" in fails, fails
    assert "nach GO" in alerts[1].text


def test_mc_drop_after_go_and_first_buyer_exit():
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    buyers = feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.5)
    engine.tick(T0 + 25)
    assert [a.tier for a in alerts] == ["GO"]
    state = engine.tokens[b58encode(mint)]
    assert state.go_mc_sol is not None
    # the first ten buyers sell everything: price falls, first-buyer exit rule -> RUG after GO
    for i, w in enumerate(buyers[:10]):
        engine.on_logs(b58encode(mint), 9500 + i, f"x{i}", None, trade_logs(mint, w, 0.45, 800_000.0, False, int(T0 + 32), creator), now=T0 + 32)
    engine.tick(T0 + 33)
    assert [a.tier for a in alerts] == ["GO", "RUG"]
    text = alerts[1].text
    assert "nach GO" in text and ("EXIT" in text or "DUMP" in text or "seit GO" in text)


def test_creation_block_wallets_are_not_outside_buyers_and_hidden_float_is_flagged():
    engine, alerts = make_engine(stufe=3)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    for i in range(6):
        engine.on_logs(b58encode(mint), 9700, f"w{i}", None, trade_logs(mint, key(), 0.5, 15_000_000.0, True, int(T0), creator), now=T0 + 0.3)
    engine.on_logs(b58encode(mint), 9720, "lone", None, trade_logs(mint, key(), 0.55, 15_000_000.0, True, int(T0 + 3), creator), now=T0 + 3)
    state = engine.tokens[b58encode(mint)]
    feats = engine.evaluate(state, T0 + 16).verdict.features
    assert feats.unique_outside_buyers == 1  # the six creation-block wallets are not organic demand
    assert [a.tier for a in alerts] == []
    # trades the engine never saw (bought before the subscription) leave a hole between curve and balances
    engine2, alerts2 = make_engine(stufe=3)
    mint2, creator2 = key(), key()
    engine2.on_launch(launch_msg(mint2, creator2), now=T0)
    curve2 = CURVES.setdefault(mint2, [30_500_000_000, 1_073_000_000_000_000 - 20_000_000_000_000])
    curve2[0] += 6_000_000_000  # 6 SOL entered the curve unseen ...
    curve2[1] -= 180_000_000_000_000  # ... buying 18 % of the supply
    feed_buyers(engine2, mint2, creator2, 8, T0 + 3, 1.0, sol=0.2)
    state2 = engine2.tokens[b58encode(mint2)]
    feats2 = engine2.evaluate(state2, T0 + 16).verdict.features
    assert feats2.hidden_float_share is not None and 0.17 < feats2.hidden_float_share < 0.19
    assert any(f.startswith("UNSICHTBAR") for f in engine2.evaluate(state2, T0 + 16).flags)
    assert [a.tier for a in alerts2] == []


def test_guessed_window_blocks_alerts_until_grace_and_idle_tokens_expire():
    engine, alerts = make_engine(stufe=3)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    # a bundle whose logs arrive late (after the 1.5 s window): the creation slot is only a guess
    for i in range(3):
        engine.on_logs(b58encode(mint), 9800, f"late{i}", None, trade_logs(mint, key(), 0.5, 15_000_000.0, True, int(T0), creator), now=T0 + 2.0)
    feed_buyers(engine, mint, creator, 5, T0 + 3, 1.0, sol=0.2, slot0=9800)
    state = engine.tokens[b58encode(mint)]
    assert state.window_guessed and not state.create_slot_known
    engine.tick(T0 + 8)
    assert alerts == []  # within the grace period nothing is sent
    engine.tick(T0 + 20)
    assert [a.tier for a in alerts] != [] or state.last_word in ("WARTE", "RUG")  # after the grace the engine decides with what it has
    # a token nobody but the dev ever traded is dropped after idle_expire_s
    engine3, _ = make_engine(stufe=2)
    m3, c3 = key(), key()
    engine3.on_launch(launch_msg(m3, c3), now=T0)
    assert engine3.tick(T0 + 30) == []
    assert engine3.tick(T0 + 61) == [b58encode(m3)]


def test_rpc_budget_skips_side_tasks():
    calls = []

    def side(name, fn, done, delay=0.0, group="rpc"):
        calls.append((name, group))
        done(None)

    class Rpc:
        stats = {"requests": 0}

    engine, alerts = make_engine(stufe=2, side=side)
    engine.rpc = Rpc()
    engine.cfg.rpc_units_per_hour = 10
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.0, sol=0.2)
    engine.tick(T0 + 10)
    assert ("create_tx", "rpc") in calls and ("creator", "rpc") in calls
    Rpc.stats["requests"] = 50  # budget for this hour exhausted
    mint2, creator2 = key(), key()
    engine.on_launch(launch_msg(mint2, creator2), now=T0 + 20)
    feed_buyers(engine, mint2, creator2, 6, T0 + 23, 1.0, sol=0.2)
    before = len(calls)
    engine.tick(T0 + 30)
    assert len(calls) == before and engine.stats["side_skipped_budget"] > 0


def test_late_transaction_does_not_roll_curve_back():
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    state = engine.tokens[b58encode(mint)]
    feed_buyers(engine, mint, creator, 3, T0 + 3, 1.0, sol=0.5, slot0=6000)
    v_sol_after = state.curve.virtual_quote_reserves
    from tests.helpers import fake_tx

    old = fake_tx("old", 5990, int(T0 + 1), key(), [TRADE_EVENT_DISC + trade_event_bytes(mint, key(), 10**8, 10**12, True, int(T0 + 1), creator)])
    engine.apply_fetched_transactions({"old": old}, now=T0 + 8)
    assert state.curve.virtual_quote_reserves == v_sol_after
    assert engine.requeue_missing(["nope"]) == 0


def test_log_stream_maps_subscriptions():
    got = []
    stream = SolanaLogStream("wss://x", "confirmed", lambda *a: got.append(a))
    stream.pending[7] = "MINT"
    stream.handle('{"jsonrpc":"2.0","result":42,"id":7}')
    assert stream.subs[42] == "MINT" and stream.mint_sub["MINT"] == 42
    stream.handle('{"jsonrpc":"2.0","method":"logsNotification","params":{"subscription":42,"result":{"context":{"slot":123},"value":{"signature":"s","err":null,"logs":["a"]}}}}')
    assert got == [("MINT", 123, "s", None, ["a"])]
    stream.handle("not json")
    stream.handle('{"jsonrpc":"2.0","method":"logsNotification","params":{"subscription":99,"result":{}}}')
    assert len(got) == 1


def test_big_dev_position_blocks_blick_and_go():
    # the dev keeps 12 % of the supply: real followers alone do not make a GO (dump risk), the control without it does
    engine, alerts = make_engine(stufe=2)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator, initial_buy_tokens=120_000_000.0, sol=3.7), now=T0)
    CURVES[mint] = [33_700_000_000, 1_073_000_000_000_000 - 120_000_000_000_000]
    feed_buyers(engine, mint, creator, 14, T0 + 3, 1.2, sol=0.12)
    engine.tick(T0 + 25)
    state = engine.tokens[b58encode(mint)]
    report = engine.evaluate(state, T0 + 26)
    assert any(f.startswith("DEV-GROSS 12%") for f in report.flags), report.flags
    assert report.word == "WARTE" and alerts == []
    control, alerts_c = make_engine(stufe=2)
    mint_c, creator_c = key(), key()
    control.on_launch(launch_msg(mint_c, creator_c), now=T0)
    feed_buyers(control, mint_c, creator_c, 14, T0 + 3, 1.2, sol=0.12)
    control.tick(T0 + 25)
    assert [a.tier for a in alerts_c] == ["GO"]
