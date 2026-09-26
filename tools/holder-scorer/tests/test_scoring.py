"""Scenario tests: organic growth, bundled dev dump, dead token, too early."""
from __future__ import annotations

import random

from holder_scorer.collect import CreatorHistory, HolderInfo, Snapshot, WalletProfile, derive_balances
from holder_scorer.encoding import b58encode
from holder_scorer.features import compute_features
from holder_scorer.pump import BondingCurveState, CreateEvent, TradeEvent, TOKEN_TOTAL_SUPPLY
from holder_scorer.scoring import (
    LABEL_NO,
    LABEL_TOO_EARLY,
    LABEL_YES,
    ScoringConfig,
    format_verdict,
    score_features,
)
from tests.helpers import key

NOW = 1_800_000_000.0
SUPPLY = TOKEN_TOTAL_SUPPLY


def addr() -> str:
    return b58encode(key())


def trade(mint: str, user: str, sol: float, share: float, is_buy: bool, ts: float, slot: int) -> TradeEvent:
    return TradeEvent(
        mint=mint,
        sol_amount=int(sol * 1e9),
        token_amount=int(share * SUPPLY),
        is_buy=is_buy,
        user=user,
        timestamp=int(ts),
        virtual_sol_reserves=0,
        virtual_token_reserves=1,
        real_sol_reserves=0,
        real_token_reserves=0,
        slot=slot,
    )


def base_snapshot(mint: str, dev: str, launch_ts: float, trades: list[TradeEvent], curve_sol: float = 10.0) -> Snapshot:
    snap = Snapshot(mint=mint, bonding_curve=addr(), collected_at=NOW)
    sold = sum(t.token_amount for t in trades if t.is_buy) - sum(t.token_amount for t in trades if not t.is_buy)
    snap.curve = BondingCurveState(
        virtual_token_reserves=1_073_000_000_000_000 - sold,
        virtual_quote_reserves=int((30 + curve_sol) * 1e9),
        real_token_reserves=793_100_000_000_000 - sold,
        real_quote_reserves=int(curve_sol * 1e9),
        token_total_supply=SUPPLY,
        complete=False,
        creator=dev,
    )
    snap.create = CreateEvent(
        name="Test", symbol="TST", uri="ipfs://x", mint=mint, bonding_curve=snap.bonding_curve, user=dev, creator=dev,
        timestamp=int(launch_ts), virtual_token_reserves=0, virtual_sol_reserves=0, real_token_reserves=0,
        token_total_supply=SUPPLY, slot=1000,
    )
    snap.trades = trades
    snap.total_signatures = len(trades) + 1
    snap.history_ok = True
    snap.holders = [HolderInfo(o, a) for o, a in derive_balances(trades).items() if a > 0]
    snap.holders_source = "trades"
    return snap


def organic_snapshot() -> Snapshot:
    rnd = random.Random(1)
    mint, dev = addr(), addr()
    launch = NOW - 150
    trades = [trade(mint, dev, 0.5, 0.02, True, launch, 1000)]
    t = launch + 3
    slot = 1008
    # 12 buyers in the first 60 s, 34 in the last 90 s (accelerating)
    for i in range(46):
        gap = 5.0 if i < 12 else 2.5
        t += gap
        slot += int(gap / 0.4)
        size = rnd.choice([0.02, 0.03, 0.05, 0.08, 0.15, 0.3])
        trades.append(trade(mint, addr(), size, size * 0.004, True, t, slot))
    sellers = list(trades[5:8])
    for i, tr in enumerate(sellers):  # three early buyers sell half of their position
        trades.append(trade(mint, tr.user, 0.02, tr.token_amount / SUPPLY * 0.5, False, launch + 100 + i * 10, 1300 + i))
    trades.sort(key=lambda x: (x.slot, x.timestamp))
    snap = base_snapshot(mint, dev, launch, trades, curve_sol=12.0)
    snap.creator_history = CreatorHistory(address=dev, prior_tokens=2, graduated=1, dead=1, source="das+rpc")
    snap.creator_profile = WalletProfile(address=dev, tx_count=900, first_seen=int(launch - 90 * 86400))
    snap.early_wallets = [WalletProfile(address=tr.user, tx_count=400, first_seen=int(launch - 30 * 86400)) for tr in trades[1:7]]
    snap.metadata = {"twitter": "https://x.com/testcoin/status/1", "telegram": "https://t.me/testcoin", "image": "https://ipfs.io/ipfs/abc"}
    snap.metadata_ok = True
    return snap


def bundle_snapshot() -> Snapshot:
    mint, dev = addr(), addr()
    launch = NOW - 200
    trades = [trade(mint, dev, 1.5, 0.05, True, launch, 1000)]
    bundle = [addr() for _ in range(8)]
    for i, w in enumerate(bundle):
        trades.append(trade(mint, w, 1.0, 0.0375, True, launch, 1000 + (i % 2)))  # 30 % in the creation block
    for i in range(6):
        trades.append(trade(mint, addr(), 0.05, 0.0005, True, launch + 10 + i * 8, 1030 + i * 20))
    trades.append(trade(mint, dev, 3.0, 0.05, False, launch + 60, 1150))  # dev dumps everything
    for i, w in enumerate(bundle[:5]):
        trades.append(trade(mint, w, 0.8, 0.0375, False, launch + 65 + i, 1160 + i))
    trades.append(trade(mint, addr(), 0.03, 0.0003, True, launch + 190, 1480))
    snap = base_snapshot(mint, dev, launch, trades, curve_sol=4.0)
    snap.creator_history = CreatorHistory(address=dev, prior_tokens=12, graduated=0, dead=11, active=1, source="rpc")
    snap.creator_profile = WalletProfile(address=dev, tx_count=15, first_seen=int(launch - 3600), is_fresh=True)
    snap.early_wallets = [WalletProfile(address=w, tx_count=3, first_seen=int(launch - 600), funder=dev, is_fresh=True) for w in bundle[:6]]
    snap.metadata_ok = True
    snap.metadata = {"twitter": "https://x.com"}
    return snap


def dead_snapshot() -> Snapshot:
    mint, dev = addr(), addr()
    launch = NOW - 400
    trades = [trade(mint, dev, 0.2, 0.01, True, launch, 1000)]
    for i in range(5):
        trades.append(trade(mint, addr(), 0.05, 0.0005, True, launch + 5 + i * 5, 1010 + i * 12))
    snap = base_snapshot(mint, dev, launch, trades, curve_sol=0.5)
    snap.creator_history = CreatorHistory(address=dev, prior_tokens=0, source="rpc")
    return snap


def young_snapshot() -> Snapshot:
    mint, dev = addr(), addr()
    launch = NOW - 20
    trades = [trade(mint, dev, 0.2, 0.01, True, launch, 1000)]
    for i in range(3):
        trades.append(trade(mint, addr(), 0.05, 0.0005, True, launch + 2 + i * 4, 1005 + i * 10))
    return base_snapshot(mint, dev, launch, trades, curve_sol=0.5)


def test_organic_token_scores_yes():
    feats = compute_features(organic_snapshot(), NOW)
    v = score_features(feats)
    assert feats.holders_now == 47  # dev + 46 buyers, three sellers sold only half
    assert feats.holders_now_trades == 47
    assert feats.holder_growth_60s is not None and feats.holder_growth_60s > 0.4
    assert feats.creation_window_share == 0.0
    assert feats.dev_buy_share == 0.02 and feats.dev_sold_share == 0.0
    assert feats.socials_count == 2
    assert feats.unique_outside_buyers == 46 and feats.bot_buy_share == 0.0
    assert feats.organic_net_flow_120s_sol is not None and feats.organic_net_flow_120s_sol > 1.0
    assert v.hard_fails == []
    assert v.label == LABEL_YES, format_verdict(v)
    assert v.score >= 80


def test_bundled_dev_dump_is_hard_no():
    feats = compute_features(bundle_snapshot(), NOW)
    v = score_features(feats)
    assert feats.creation_slot_buyers == 8
    assert 0.29 < feats.creation_window_share < 0.31
    assert feats.creation_window_sold_share is not None and 0.6 < feats.creation_window_sold_share < 0.65
    assert feats.early_sold_share is not None and feats.early_sold_share > 0.5
    assert feats.dev_sold_share == 1.0
    assert feats.early_fresh_wallets == 6 and feats.early_funded_by_creator == 6
    assert v.label == LABEL_NO
    assert any("Dev-Dump" in r for r in v.hard_fails)
    assert any("Serien-Deployer" in r for r in v.hard_fails)
    assert v.score < 45


def coordinated_snapshot() -> Snapshot:
    """Dev plus four coordinated wallets and not a single outside buyer: must never be JA."""
    mint, dev = addr(), addr()
    launch = NOW - 100
    ring = [addr() for _ in range(4)]
    trades = [trade(mint, dev, 0.3, 0.01, True, launch, 1000)]
    slot = 1010
    t = launch + 5
    for i in range(24):  # the four wallets take turns buying every ~4 s with the same size
        w = ring[i % 4]
        t += 3.8
        slot += 15
        trades.append(trade(mint, w, 0.05, 0.0005, True, t, slot))
    snap = base_snapshot(mint, dev, launch, trades, curve_sol=2.0)
    snap.creator_history = CreatorHistory(address=dev, prior_tokens=0, source="rpc")
    snap.creator_profile = WalletProfile(address=dev, tx_count=300, first_seen=int(launch - 40 * 86400))
    snap.early_wallets = [WalletProfile(address=w, tx_count=150, first_seen=int(launch - 20 * 86400)) for w in ring]
    snap.metadata_ok = True
    snap.metadata = {"twitter": "https://x.com/ring/status/1", "telegram": "https://t.me/ring", "website": "https://ring.example/x", "image": "https://ipfs.io/ipfs/a"}
    return snap


def test_coordinated_wallets_cannot_reach_yes():
    feats = compute_features(coordinated_snapshot(), NOW)
    v = score_features(feats)
    assert feats.unique_outside_buyers == 0  # all four wallets are repeat buyers, i.e. bots
    assert feats.bot_buy_share == 1.0
    assert v.label != LABEL_YES, format_verdict(v)


def test_dead_token_is_no():
    v = score_features(compute_features(dead_snapshot(), NOW))
    assert v.label == LABEL_NO
    assert any("eingeschlafen" in r for r in v.hard_fails)


def test_young_token_is_too_early_but_can_be_forced():
    feats = compute_features(young_snapshot(), NOW)
    assert score_features(feats).label == LABEL_TOO_EARLY
    forced = score_features(feats, ScoringConfig(min_age_s=0, yes_threshold=30))
    assert forced.label in (LABEL_YES, "UNKLAR", LABEL_NO)
    assert forced.features.holder_growth_60s is None  # too young for a 60 s comparison


def test_verdict_serialises_and_formats():
    v = score_features(compute_features(organic_snapshot(), NOW))
    d = v.to_dict()
    assert d["label"] == LABEL_YES and isinstance(d["features"]["holders_now"], int)
    text = format_verdict(v)
    assert "Score" in text and "Holder-Momentum" in text
