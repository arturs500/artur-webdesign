import pytest

from holder_scorer.encoding import BorshError, b58encode
from holder_scorer.pump import (
    IX_CREATE,
    decode_bonding_curve,
    decode_create_event,
    decode_trade_event,
    parse_transaction,
)
from tests.helpers import (
    CREATE_EVENT_DISC,
    TRADE_EVENT_DISC,
    bonding_curve_bytes,
    create_event_bytes,
    fake_tx,
    key,
    trade_event_bytes,
)


def test_decode_trade_event_full_and_legacy():
    mint, user, creator = key(), key(), key()
    full = decode_trade_event(trade_event_bytes(mint, user, 2_000_000_000, 50_000_000_000_000, True, 1_700_000_000, creator, full=True))
    assert full.mint == b58encode(mint)
    assert full.user == b58encode(user)
    assert full.creator == b58encode(creator)
    assert full.sol_amount == 2_000_000_000 and full.token_amount == 50_000_000_000_000
    assert full.is_buy is True and full.timestamp == 1_700_000_000
    assert full.ix_name == "buy"
    assert full.quote_amount == 2_000_000_000
    legacy = decode_trade_event(trade_event_bytes(mint, user, 5, 7, False, 1, full=False))
    assert legacy.creator is None and legacy.ix_name is None
    assert legacy.is_buy is False and legacy.sol_amount == 5 and legacy.token_amount == 7
    with pytest.raises(BorshError):
        decode_trade_event(b"\x00" * 10)


def test_decode_create_event():
    mint, curve, user, creator = key(), key(), key(), key()
    ev = decode_create_event(create_event_bytes("Test Coin", "TST", "https://x.test/meta.json", mint, curve, user, creator, 42))
    assert (ev.name, ev.symbol, ev.uri) == ("Test Coin", "TST", "https://x.test/meta.json")
    assert ev.mint == b58encode(mint) and ev.bonding_curve == b58encode(curve)
    assert ev.user == b58encode(user) and ev.creator == b58encode(creator)
    assert ev.timestamp == 42 and ev.token_total_supply == 1_000_000_000_000_000


def test_decode_bonding_curve_new_and_old_layout():
    creator = key()
    st = decode_bonding_curve(bonding_curve_bytes(1_000, 40_000_000_000, 500_000_000_000_000, 10_000_000_000, 1_000_000_000_000_000, False, creator))
    assert st.creator == b58encode(creator)
    assert st.complete is False
    assert 0.36 < st.progress < 0.37
    old = decode_bonding_curve(bonding_curve_bytes(1, 2, 0, 3, 4, True, new_layout=False))
    assert old.complete is True and old.creator is None and st.quote_is_sol
    with pytest.raises(BorshError):
        decode_bonding_curve(b"\x01" * 60)


def test_parse_transaction_cpi_and_logs_and_failed():
    mint, user, payer = key(), key(), key()
    trade = TRADE_EVENT_DISC + trade_event_bytes(mint, user, 10, 20, True, 100)
    create = CREATE_EVENT_DISC + create_event_bytes("n", "s", "u", mint, key(), payer, payer, 100)
    tx_cpi = fake_tx("sig1", 500, 100, payer, [create, trade], via="cpi")
    parsed = parse_transaction("sig1", tx_cpi)
    assert parsed is not None and not parsed.failed
    assert parsed.slot == 500 and parsed.fee_payer == b58encode(payer)
    assert len(parsed.trades) == 1 and parsed.trades[0].signature == "sig1" and parsed.trades[0].slot == 500
    assert parsed.created_mints == [b58encode(mint)] and parsed.creates[0].name == "n"

    tx_log = fake_tx("sig2", 501, 101, payer, [trade], via="log")
    parsed2 = parse_transaction("sig2", tx_log)
    assert len(parsed2.trades) == 1 and parsed2.trades[0].block_time == 101

    both = fake_tx("sig3", 502, 102, payer, [trade], via="cpi")
    both["meta"]["logMessages"].append(tx_log["meta"]["logMessages"][-1])
    assert len(parse_transaction("sig3", both).trades) == 1  # deduplicated

    failed = parse_transaction("sig4", fake_tx("sig4", 503, 103, payer, [trade], failed=True))
    assert failed.failed and failed.trades == []
    assert parse_transaction("sig5", None) is None


def test_parse_transaction_create_fallback_from_instruction():
    mint, payer = key(), key()
    tx = fake_tx("sig", 1, 1, payer, [], extra_instructions=[{"programIdIndex": 1, "accounts": [2], "data": b58encode(IX_CREATE + b"\x00" * 4)}])
    tx["transaction"]["message"]["accountKeys"][2] = b58encode(mint)
    parsed = parse_transaction("sig", tx)
    assert parsed.created_mints == [b58encode(mint)]
