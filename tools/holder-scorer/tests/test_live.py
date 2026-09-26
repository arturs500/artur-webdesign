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
from holder_scorer.scoring import ScoringConfig
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
    assert s1.min_age_s == 90 and s3.min_age_s == 12 and s3.yes_min_outside_buyers == 4 and s3.yes_threshold == 55
    engine, alerts = make_engine(stufe=3)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    feed_buyers(engine, mint, creator, 4, T0 + 2, 1.0, sol=0.1)
    engine.tick(T0 + 7)
    assert [a.tier for a in alerts] == ["BLICK"]


def test_missing_event_fallback_and_side_tasks():
    calls = []

    def side(name, fn, done):
        calls.append(name)
        if name == "creator":
            done((CreatorHistory(address="c", prior_tokens=1, graduated=1, source="rpc"), None, None))
        else:
            done(None)

    engine, alerts = make_engine(stufe=2, side=side)
    engine.rpc = object()  # side tasks are only scheduled when an rpc exists
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    assert "create_tx" in calls  # scheduled at launch (metadata not: uri is empty)
    # a log without a decodable event is queued for a getTransaction fallback
    engine.on_logs(b58encode(mint), 6000, "cpi-only", None, [PUMP_LOG, "Program log: Instruction: Buy"], now=T0 + 2)
    assert engine.take_missing() == ["cpi-only"] and engine.take_missing() == []
    from tests.helpers import fake_tx

    payer = key()
    tx = fake_tx("cpi-only", 6000, int(T0 + 2), payer, [TRADE_EVENT_DISC + trade_event_bytes(mint, payer, 10**8, 10**12, True, int(T0 + 2), creator)])
    assert engine.apply_fetched_transactions({"cpi-only": tx}, now=T0 + 3) == 1
    assert engine.apply_fetched_transactions({"cpi-only": tx}, now=T0 + 3) == 0  # deduplicated
    feed_buyers(engine, mint, creator, 5, T0 + 4, 1.0)
    engine.tick(T0 + 10)
    assert "creator" in calls and "profiles" in calls
    state = engine.tokens[b58encode(mint)]
    assert state.creator_history is not None and state.creator_history.prior_tokens == 1


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
