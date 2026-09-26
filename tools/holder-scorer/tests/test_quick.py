"""Schnellcheck: market parsing, rug rules, words, short messages, early config."""
from __future__ import annotations

import holder_scorer.quick as quick_mod
from holder_scorer.features import compute_features
from holder_scorer.market import MarketData, parse_pairs
from holder_scorer.notify import fmt_usd, format_legend, format_short
from holder_scorer.quick import QuickConfig, QuickReport, market_flags, quick_check, word_for
from holder_scorer.scoring import ScoringConfig, score_features, short_flags
from tests.test_collect import FakeRpc, build_token
from tests.test_scoring import NOW, bundle_snapshot, dead_snapshot, organic_snapshot

MINT = "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"
WSOL = "So11111111111111111111111111111111111111112"


def pair(mc, vol_h1, liq, dex="pumpswap", quote=WSOL, created_ms=1_700_000_000_000, price_usd="0.0009", price_native="0.000006"):
    return {
        "chainId": "solana",
        "dexId": dex,
        "pairAddress": "pairX",
        "baseToken": {"address": MINT, "name": "Fart Coin", "symbol": "FART"},
        "quoteToken": {"address": quote, "symbol": "SOL"},
        "priceUsd": price_usd,
        "priceNative": price_native,
        "txns": {"m5": {"buys": 3, "sells": 1}, "h1": {"buys": 40, "sells": 22}},
        "volume": {"m5": 300.0, "h1": vol_h1, "h24": vol_h1 * 3},
        "priceChange": {"m5": 1.2, "h1": -5.0},
        "liquidity": {"usd": liq, "base": 1e9, "quote": liq / 300},
        "fdv": mc,
        "marketCap": mc,
        "pairCreatedAt": created_ms,
        "info": {"websites": [{"url": "https://x.example"}], "socials": [{"type": "twitter", "url": "https://x.com/a/status/1"}]},
    }


def test_parse_pairs_picks_most_liquid_sol_pair_and_sol_price():
    payload = {"pairs": [pair(900_000, 5_000, 5_000, dex="raydium"), pair(880_000, 7_000, 12_000), pair(1, 1, 99_999, quote="USDCmint")]}
    md = parse_pairs(payload, MINT)
    assert md is not None and md.liquidity_usd == 12_000 and md.dex_id == "pumpswap"
    assert md.market_cap_usd == 880_000 and md.volume_h1_usd == 7_000 and md.buys_h1 == 40
    assert md.pair_created_at == 1_700_000_000.0
    assert md.socials == 2 and md.symbol == "FART"
    assert md.sol_usd is not None and abs(md.sol_usd - 150.0) < 1e-6
    assert parse_pairs({"pairs": None}, MINT) is None
    assert parse_pairs(None, MINT) is None


def test_market_flags_fake_mc_and_thin():
    rug = parse_pairs({"pairs": [pair(900_000, 5_000, 5_000)]}, MINT)
    flags = market_flags(rug, "graduated", QuickConfig())
    assert any(f.startswith("FAKE-MC") for f in flags) and any(f.startswith("DÜNN") for f in flags)
    healthy = parse_pairs({"pairs": [pair(900_000, 400_000, 120_000)]}, MINT)
    assert market_flags(healthy, "graduated", QuickConfig()) == []
    small = parse_pairs({"pairs": [pair(8_000, 100, 200)]}, MINT)
    assert market_flags(small, "curve", QuickConfig()) == []  # below the MC floor the rule is meaningless
    assert word_for(None, ["FAKE-MC 0.006"], "graduated") == "RUG"
    assert word_for(None, [], "graduated") == "GRAD"


def test_words_and_flags_from_onchain_verdicts():
    cfg = ScoringConfig()
    organic = score_features(compute_features(organic_snapshot(), NOW), cfg)
    assert word_for(organic, short_flags(organic.features, cfg), "curve") == "GO"
    bundle = score_features(compute_features(bundle_snapshot(), NOW), cfg)
    flags = short_flags(bundle.features, cfg)
    assert any(f.startswith("BUNDLE 30%") for f in flags) and "DEV-DUMP" in flags
    assert any(f.startswith("SERIE 12/0/11") for f in flags) and any(f.startswith("FRISCH 6/6") for f in flags)
    assert word_for(bundle, flags, "curve") == "RUG"
    dead = score_features(compute_features(dead_snapshot(), NOW), cfg)
    dflags = short_flags(dead.features, cfg)
    assert any(f.startswith("STILL") for f in dflags)
    assert word_for(dead, dflags, "curve") == "TOT"


def test_features_market_numbers():
    feats = compute_features(organic_snapshot(), NOW)
    assert feats.mc_sol is not None and 25 < feats.mc_sol < 200
    assert feats.volume_sol is not None and feats.volume_sol > 3
    assert feats.turnover is not None and feats.turnover > 0
    assert feats.liq_to_mc is not None and 0 < feats.liq_to_mc < 1
    assert feats.volume_60s_sol is not None and feats.volume_60s_sol <= feats.volume_sol


def test_quick_check_curve_token_with_market(monkeypatch):
    mint, dev, curve, sigs, txs = build_token(n_buys=5)
    rpc = FakeRpc(mint, curve, sigs, txs)
    monkeypatch.setattr(quick_mod, "fetch_market", lambda m, **kw: parse_pairs({"pairs": [pair(6_000, 900, 1_500, dex="pumpfun")]}, m))
    monkeypatch.setattr(quick_mod, "sol_usd", lambda hint=None, **kw: hint or 150.0)
    report = quick_check(mint, rpc, quick=QuickConfig(fast=True), now=NOW)
    assert report.phase == "curve" and report.verdict is not None
    assert report.sol_usd == 150.0
    assert report.mc_sol is not None and report.mc_usd is not None and abs(report.mc_usd - report.mc_sol * 150.0) < 1e-6
    assert report.holders == 6 and report.dev_share == 0.02 and report.bundle_share == 0.0
    # the synthetic token is 200 s old and its last trade was 70 s ago: early stall rule -> TOT
    assert report.word == "TOT" and any(f.startswith("STILL") for f in report.flags)
    text = format_short(report)
    lines = text.split("\n")
    assert len(lines) == 10 and lines[0].startswith("⚫ TOT")
    assert lines[1].startswith("MC   ") and lines[4].startswith("Hold 6")
    assert all(len(line) <= 90 for line in lines)
    d = report.to_dict()
    assert d["verdict"]["label"] == report.verdict.label and d["market"]["dex_id"] == "pumpfun"


def test_quick_check_graduated_token_uses_market_only(monkeypatch):
    mint, dev, curve, sigs, txs = build_token(n_buys=2)
    from tests.helpers import bonding_curve_bytes

    graduated = bonding_curve_bytes(1, 115_000_000_000, 0, 85_000_000_000, 1_000_000_000_000_000, True)
    rpc = FakeRpc(mint, graduated, sigs, txs, das=[{"address": f"a{i}", "owner": f"o{i}", "amount": 5 * 10**12} for i in range(40)])
    monkeypatch.setattr(quick_mod, "fetch_market", lambda m, **kw: parse_pairs({"pairs": [pair(900_000, 5_000, 5_000)]}, m))
    monkeypatch.setattr(quick_mod, "sol_usd", lambda hint=None, **kw: hint or 150.0)
    report = quick_check(mint, rpc, now=NOW)
    assert report.phase == "graduated" and report.verdict is None
    assert report.word == "RUG" and any(f.startswith("FAKE-MC") for f in report.flags)
    assert report.holders == 40 and report.mc_usd == 900_000 and report.turnover is not None and report.turnover < 0.01
    assert not any(c.startswith("getTransaction") for c in rpc.calls)  # no trade history for graduated tokens
    text = format_short(report)
    assert text.startswith("🔴 RUG · FART") and "FAKE-MC" in text and "DÜNN" in text


def test_quick_check_without_market_and_unknown_token(monkeypatch):
    mint, dev, curve, sigs, txs = build_token(n_buys=3)
    rpc = FakeRpc(mint, None, sigs, txs)
    monkeypatch.setattr(quick_mod, "fetch_market", lambda m, **kw: None)
    report = quick_check(mint, rpc, quick=QuickConfig(use_market=False), now=NOW)
    assert report.phase == "unknown" and report.word == "?"
    assert format_short(report).startswith("❔ ?")


def test_early_config_and_legend():
    cfg = ScoringConfig.early()
    assert cfg.min_age_s == 20 and cfg.yes_min_outside_buyers == 6 and cfg.early_stall_gap_s == 25
    legend = format_legend()
    for word in ("GO", "WARTE", "RUG", "TOT", "GRAD", "FAKE-MC", "BUNDLE"):
        assert word in legend
    assert fmt_usd(900_000) == "900k$" and fmt_usd(1_250_000) == "1.25M$" and fmt_usd(5_000) == "5.0k$" and fmt_usd(12) == "12$"


def test_format_short_handles_missing_values():
    r = QuickReport(mint=MINT, word="?", phase="unknown")
    text = format_short(r)
    assert "MC   ?" in text and "Hold ?" in text and text.endswith("⚠️   –")


def test_every_flag_word_has_a_legend_entry():
    import inspect
    import re

    from holder_scorer import notify, quick, scoring

    src = inspect.getsource(scoring.short_flags) + inspect.getsource(quick)
    heads = set(re.findall(r'flags\.append\(f?"([A-ZÄÖÜ0-9-]+)', src))
    assert "BUNDLE" in heads and "DEV-GROSS" in heads and "FAKE-MC" in heads
    assert heads <= set(notify.FLAGS), heads - set(notify.FLAGS)
