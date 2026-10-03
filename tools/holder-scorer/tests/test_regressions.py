"""Regression tests for the findings of the second review round."""
from __future__ import annotations

import json

from holder_scorer.calibrate import load_records, update_outcomes
from holder_scorer.collect import ProfileCache, collect
from holder_scorer.encoding import b58encode
from holder_scorer.features import compute_features
from holder_scorer.pump import derive_bonding_curve
from holder_scorer.scoring import ScoringConfig, score_features
from tests.helpers import CREATE_EVENT_DISC, TRADE_EVENT_DISC, bonding_curve_bytes, create_event_bytes, fake_tx, key, trade_event_bytes
from tests.test_collect import FakeRpc, build_token
from tests.test_scoring import NOW, organic_snapshot


class CreatorRpc(FakeRpc):
    """FakeRpc that also serves a creator wallet history with several create transactions."""

    def __init__(self, *args, creator: str, creator_sigs: list[dict], creator_txs: dict, curves: dict, **kw):
        super().__init__(*args, **kw)
        self.creator = creator
        self.creator_sigs = creator_sigs
        self.creator_txs = creator_txs
        self.curves = curves  # bonding-curve address -> data

    def get_signatures(self, address, limit=1000, before=None):
        if address == self.creator:
            self.calls.append("getSignaturesForAddress(creator)")
            return list(self.creator_sigs)[:limit]
        return super().get_signatures(address, limit, before)

    def get_transactions(self, signatures):
        out = super().get_transactions(signatures)
        for s in signatures:
            if s in self.creator_txs:
                out[s] = self.creator_txs[s]
        return out

    def get_multiple_account_data(self, addresses):
        self.calls.append("getMultipleAccounts")
        return [self.curves.get(a) for a in addresses]


def serial_creator_setup():
    """Creator launches token A at T-300 and token B at T; both histories are complete."""
    dev = key()
    dev_s = b58encode(dev)
    tokens = {}
    creator_sigs, creator_txs, curves = [], {}, {}
    for name, launch in (("A", int(NOW) - 300), ("B", int(NOW))):
        mint = key()
        mint_s = b58encode(mint)
        create = CREATE_EVENT_DISC + create_event_bytes(name, name, "", mint, key(), dev, dev, launch)
        dev_buy = TRADE_EVENT_DISC + trade_event_bytes(mint, dev, 300_000_000, 10_000_000_000_000, True, launch, dev)
        sig = f"create{name}"
        tx = fake_tx(sig, 1000 if name == "A" else 2000, launch, dev, [create, dev_buy])
        txs = {sig: tx}
        sigs = [{"signature": sig, "slot": tx["slot"], "blockTime": launch, "err": None}]
        for i in range(8):
            buyer = key()
            ev = TRADE_EVENT_DISC + trade_event_bytes(mint, buyer, 40_000_000, 800_000_000_000, True, launch + 10 + i * 10, dev)
            bsig = f"buy{name}{i}"
            txs[bsig] = fake_tx(bsig, tx["slot"] + 30 + i * 25, launch + 10 + i * 10, buyer, [ev])
            sigs.append({"signature": bsig, "slot": txs[bsig]["slot"], "blockTime": launch + 10 + i * 10, "err": None})
        sigs.reverse()
        curve = bonding_curve_bytes(1_000_000_000_000_000, 31_000_000_000, 780_000_000_000_000, 1_000_000_000, 1_000_000_000_000_000, False, dev)
        curves[derive_bonding_curve(mint_s)] = curve
        tokens[name] = (mint_s, curve, sigs, txs)
        creator_sigs.append({"signature": sig, "slot": tx["slot"], "blockTime": launch, "err": None})
        creator_txs[sig] = tx
    creator_sigs.reverse()  # newest first
    return dev_s, tokens, creator_sigs, creator_txs, curves


def test_creator_cache_is_launch_independent():
    dev, tokens, creator_sigs, creator_txs, curves = serial_creator_setup()
    cache = ProfileCache()
    results = {}
    for name in ("A", "B"):
        mint, curve, sigs, txs = tokens[name]
        rpc = CreatorRpc(mint, curve, sigs, txs, creator=dev, creator_sigs=creator_sigs, creator_txs=creator_txs, curves=curves)
        snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW + (0 if name == "B" else -300), cache=cache)
        results[name] = (snap, rpc)
    snap_b, rpc_b = results["B"]
    ch = snap_b.creator_history
    assert ch.prior_tokens == 1 and ch.young == 1  # token A, launched 5 minutes earlier
    assert ch.prev_launch_ts == NOW - 300
    feats = compute_features(snap_b, NOW)
    assert feats.creator_seconds_since_prev_launch == 300
    v = score_features(feats)
    creator_factor = next(x for x in v.factors if x.name == "Creator-Historie")
    assert creator_factor.points == 0.0 and "voriger Launch" in creator_factor.comment
    # the cache hit refreshed with one cheap signature call instead of the full page + scan
    assert cache.hits == 1
    assert rpc_b.calls.count("getSignaturesForAddress(creator)") == 1
    # token A must not count itself; the fake creator history already contains B, which is later, not "previous"
    snap_a, _ = results["A"]
    assert snap_a.creator_history.prior_tokens == 1 and snap_a.creator_history.prev_launch_ts is None


def test_unknown_holder_count_does_not_cap_momentum():
    snap = organic_snapshot()
    snap.partial_history = True
    snap.holders = sorted(snap.holders, key=lambda h: -h.amount)[:20]
    snap.holders_source = "largest"
    feats = compute_features(snap, NOW)
    assert feats.holders_now is None and feats.holders_listed == 20
    v = score_features(feats)
    momentum = next(x for x in v.factors if x.name == "Holder-Momentum")
    assert momentum.points > 0.2 * ScoringConfig().w_momentum
    assert "zu wenige Holder" not in momentum.comment


def test_hot_token_keeps_bundle_and_dev_features(monkeypatch):
    mint, dev, curve, sigs, txs = build_token(n_buys=12)
    rpc = FakeRpc(mint, curve, sigs, txs)
    import importlib

    collect_mod = importlib.import_module("holder_scorer.collect")
    monkeypatch.setattr(collect_mod, "HEAD_TX", 4)
    snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW, max_tx=8)
    assert snap.partial_history and snap.head_complete and snap.head_usable and not snap.history_complete
    assert snap.head_last_slot is not None
    assert len({t.signature for t in snap.trades}) == len(snap.trades)  # no duplicates from head/tail overlap
    feats = compute_features(snap, NOW)
    assert feats.creation_window_share == 0.0 and feats.dev_buy_share == 0.02
    assert feats.dev_sold_share is None and feats.holder_growth_60s is None  # need the full history or DAS


def test_small_max_tx_never_overfetches():
    mint, dev, curve, sigs, txs = build_token(n_buys=12)
    for max_tx in (60, 40, 5):
        rpc = FakeRpc(mint, curve, sigs, txs)
        snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW, max_tx=max_tx)
        fetched = sum(int(c.split("x")[1]) for c in rpc.calls if c.startswith("getTransaction"))
        assert fetched <= max_tx
        assert len({t.signature for t in snap.trades}) == len(snap.trades)


def test_exactly_full_signature_page_is_head_complete():
    mint, dev, curve, sigs, txs = build_token(n_buys=3)

    class PagedRpc(FakeRpc):
        def get_signatures(self, address, limit=1000, before=None):
            if address == self.mint and before is None:
                self.calls.append("page1")
                return list(self.sigs) + [{"signature": f"pad{i}", "slot": 1, "blockTime": NOW - 1000, "err": {"x": 1}} for i in range(1000 - len(self.sigs))]
            if address == self.mint:
                self.calls.append("page2")
                return []
            return []

    rpc = PagedRpc(mint, curve, sigs, txs)
    snap = collect(mint, rpc, deep=False, fetch_metadata=False, now=NOW)
    assert snap.total_signatures == 1000 and snap.head_complete and "page2" in rpc.calls
    assert snap.create is not None


def test_outcome_errors_are_retried_and_prefilter_records_kept(tmp_path):
    import time

    path = str(tmp_path / "obs.jsonl")
    mint, dev, curve, sigs, txs = build_token()
    recorded_at = time.time() - 5000
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"recorded_at": recorded_at, "mint": mint, "label": "JA", "features": {"holders_now": 4}, "outcome": None}) + "\n")
        fh.write(json.dumps({"recorded_at": recorded_at, "mint": mint, "label": "VORFILTER", "signatures": 2, "features": None, "outcome": None}) + "\n")

    class FailingRpc(FakeRpc):
        def get_account_data(self, address):
            raise RuntimeError("boom")

    assert update_outcomes(path, FailingRpc(mint, curve, sigs, txs)) == 2
    recs = load_records(path)
    assert recs[0]["outcome"]["error"] == "boom" and recs[0]["outcome"]["attempts"] == 1
    das = [{"address": f"a{i}", "owner": b58encode(key()), "amount": 5 * 10**12} for i in range(30)]
    ok = FakeRpc(mint, curve, sigs, txs, das=das)
    assert update_outcomes(path, ok) == 2  # both records are re-checked after the error
    recs = load_records(path)
    assert recs[0]["outcome"]["grew"] is True and recs[0]["outcome"]["holders_later"] == 30 and recs[0]["outcome"]["attempts"] == 2
    assert recs[1]["outcome"]["grew"] is None and recs[1]["outcome"]["holders_later"] == 30
    assert update_outcomes(path, ok) == 0  # both are final now
