"""collect() and features against a fake RPC built from synthetic transactions."""
from __future__ import annotations

import threading

import pytest

from holder_scorer import cli
from holder_scorer.collect import collect
from holder_scorer.encoding import b58encode
from holder_scorer.features import _social_link_ok, compute_features
from holder_scorer.pump import derive_bonding_curve
from holder_scorer.rpc import RpcError
from tests.helpers import CREATE_EVENT_DISC, TRADE_EVENT_DISC, bonding_curve_bytes, create_event_bytes, fake_tx, key, trade_event_bytes

NOW = 1_800_000_000


class FakeRpc:
    def __init__(self, mint: str, curve_data: bytes | None, sigs: list[dict], txs: dict, das=None, fail_tx=(), curve_error=False):
        self.mint = mint
        self.curve = derive_bonding_curve(mint)
        self.curve_data = curve_data
        self.sigs = sigs
        self.txs = txs
        self.das = das
        self.fail_tx = set(fail_tx)
        self.curve_error = curve_error
        self.stop = threading.Event()
        self.das_supported = das is not None
        self.calls: list[str] = []

    def get_account_data(self, address):
        self.calls.append("getAccountInfo")
        if self.curve_error:
            raise RpcError("HTTP 401: bad key", http_status=401)
        return self.curve_data if address == self.curve else None

    def get_signatures(self, address, limit=1000, before=None):
        self.calls.append("getSignaturesForAddress")
        if address == self.mint and before is None:
            return list(self.sigs)
        return []

    def get_transactions(self, signatures):
        self.calls.append(f"getTransaction x{len(signatures)}")
        return {s: (None if s in self.fail_tx else self.txs.get(s)) for s in signatures}

    def das_get_token_accounts(self, mint, max_pages=5):
        self.calls.append("getTokenAccounts")
        return self.das

    def get_token_largest_accounts(self, mint):
        return []

    def get_token_account_owners(self, addresses):
        return {}

    def get_multiple_account_data(self, addresses):
        return [None] * len(addresses)


def build_token(n_buys: int = 5):
    mint, dev = key(), key()
    mint_s = b58encode(mint)
    create = CREATE_EVENT_DISC + create_event_bytes("T", "T", "", mint, key(), dev, dev, NOW - 200)
    dev_buy = TRADE_EVENT_DISC + trade_event_bytes(mint, dev, 500_000_000, 20_000_000_000_000, True, NOW - 200, dev)
    txs = {"create": fake_tx("create", 1000, NOW - 200, dev, [create, dev_buy])}
    sigs = [{"signature": "create", "slot": 1000, "blockTime": NOW - 200, "err": None}]
    for i in range(n_buys):
        buyer = key()
        ev = TRADE_EVENT_DISC + trade_event_bytes(mint, buyer, 50_000_000, 1_000_000_000_000, True, NOW - 150 + i * 20, dev)
        sig = f"buy{i}"
        txs[sig] = fake_tx(sig, 1100 + i * 50, NOW - 150 + i * 20, buyer, [ev])
        sigs.append({"signature": sig, "slot": 1100 + i * 50, "blockTime": NOW - 150 + i * 20, "err": None})
    sigs.append({"signature": "failed", "slot": 1400, "blockTime": NOW - 40, "err": {"x": 1}})
    sigs.reverse()  # newest first, as the RPC returns them
    curve = bonding_curve_bytes(1_000_000_000_000_000, 31_000_000_000, 768_100_000_000_000, 1_000_000_000, 1_000_000_000_000_000, False, dev)
    return mint_s, b58encode(dev), curve, sigs, txs


def test_collect_complete_history_and_features():
    mint, dev, curve, sigs, txs = build_token()
    rpc = FakeRpc(mint, curve, sigs, txs)
    snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW)
    assert snap.create is not None and snap.create.creator == dev
    assert snap.history_complete and snap.failed_tx == 1 and snap.missing_tx == 0
    assert len(snap.trades) == 6 and snap.trades[0].user == dev
    assert snap.holders_source == "trades" and len(snap.holders) == 6
    feats = compute_features(snap, NOW)
    assert feats.age_s == 200 and feats.age_source == "create"
    assert feats.holders_now == 6 and feats.creation_window_share == 0.0
    assert feats.dev_buy_share == 0.02
    assert feats.failed_after_30s_share == 1 / 6  # one failed signature among the six after +30 s


def test_collect_marks_missing_transactions_as_partial():
    mint, dev, curve, sigs, txs = build_token()
    rpc = FakeRpc(mint, curve, sigs, txs, fail_tx={"buy2"})
    snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW)
    assert snap.partial_history and snap.missing_tx == 1 and snap.history_ok
    assert any("could not be fetched" in n for n in snap.notes)
    assert sum(1 for c in rpc.calls if c.startswith("getTransaction")) == 2  # retried once
    feats = compute_features(snap, NOW)
    assert feats.creation_window_share is None and feats.dev_buy_share is None
    assert feats.holders_now is None and feats.top10_share is None


def test_collect_prefers_das_holders_and_excludes_curve():
    mint, dev, curve, sigs, txs = build_token()
    curve_pda = derive_bonding_curve(mint)
    das = [{"address": "a", "owner": curve_pda, "amount": 10**15}, {"address": "b", "owner": dev, "amount": 5 * 10**12}]
    das += [{"address": f"c{i}", "owner": b58encode(key()), "amount": 2 * 10**12} for i in range(9)]
    rpc = FakeRpc(mint, curve, sigs, txs, das=das)
    snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW)
    assert snap.holders_source == "das" and len(snap.holders) == 10
    feats = compute_features(snap, NOW)
    assert feats.holders_now == 10 and feats.holders_now_trades == 6
    assert feats.largest_float_share is not None and feats.largest_float_share < 0.2


def test_collect_raises_on_rpc_failure_and_cli_exits_2(monkeypatch):
    mint, dev, curve, sigs, txs = build_token()
    rpc = FakeRpc(mint, curve, sigs, txs, curve_error=True)
    with pytest.raises(RpcError):
        collect(mint, rpc, now=NOW)

    def boom(*args, **kwargs):
        raise RpcError("HTTP 401: bad key", http_status=401)

    monkeypatch.setattr(cli, "evaluate_token", boom)
    monkeypatch.setattr(cli, "make_rpc", lambda *a, **k: rpc)
    assert cli.main(["score", mint, "--json"]) == 2


def test_social_link_check():
    assert not _social_link_ok("httpfoo.bar/abc")
    assert not _social_link_ok("https:/x.com/a")
    assert not _social_link_ok("http-nonsense")
    assert not _social_link_ok("https://x.com")
    assert not _social_link_ok("https://t.me/")
    assert not _social_link_ok(None)
    assert _social_link_ok("https://x.com/a")
    assert _social_link_ok("HTTPS://t.me/mygroup ")
