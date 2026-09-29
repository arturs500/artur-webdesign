"""Schnellcheck: the key numbers, a one-word verdict and the warning flags.

Combines the on-chain analysis (bonding-curve tokens) with market numbers
from DexScreener (any token, also after graduation), derives the numbers a
trader looks at first (MC, volume, V/MC, liquidity, holders, buys/sells, dev,
bundle, creator) and applies the rug rules that only need those numbers:

* FAKE-MC: market cap high, but the traded volume is a tiny fraction of it
* DÜNN: liquidity a tiny fraction of the market cap (post-graduation pools)

The on-chain verdict from ``scoring.py`` is folded into one word.
"""
from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any

from .collect import ProfileCache, collect
from .encoding import BorshError
from .features import Features, compute_features
from .market import MarketData, fetch_market, sol_usd
from .pump import decode_bonding_curve, derive_bonding_curve
from .rpc import RpcError, SolanaRpc
from .scoring import (
    LABEL_GRADUATED,
    LABEL_NO,
    LABEL_NO_DATA,
    LABEL_TOO_EARLY,
    LABEL_UNCLEAR,
    LABEL_YES,
    ScoringConfig,
    Verdict,
    score_features,
    short_flags,
)

RUG_FLAGS = {"BUNDLE", "DEV-DUMP", "SERIE", "TOP1", "TOP10", "WASH", "FAKE-MC", "DÜNN", "FUNDER", "EXIT", "DUMP"}
GO_BLOCKING_FLAGS = RUG_FLAGS | {"DEV-RAUS", "DEV-GROSS", "SCHNELL", "FRISCH", "BOTS", "SELF-PUMP", "STILL", "MAYHEM", "USDC", "UNSICHTBAR"}
GO_MAX_BUNDLE_SHARE = 0.10  # a bundle at or above this share turns a JA into WARTE (below it the flag still shows)


def _bundle_share_from_flag(flag: str) -> float | None:
    try:
        return float(flag.split(" ")[1].split("/")[0].rstrip("%")) / 100.0
    except (IndexError, ValueError):
        return None


def go_blockers(flags: list[str], max_bundle_share: float = GO_MAX_BUNDLE_SHARE) -> list[str]:
    """Flags that keep a JA verdict from becoming GO."""
    out: list[str] = []
    for f in flags:
        head = f.split(" ")[0]
        if head == "BUNDLE":
            share = _bundle_share_from_flag(f)
            if share is not None and share >= max_bundle_share:
                out.append(f)
        elif head in GO_BLOCKING_FLAGS:
            out.append(f)
    return out


@dataclass
class QuickConfig:
    fake_mc_min_usd: float = 50_000.0  # below this MC the volume rule is meaningless
    fake_mc_max_turnover_h1: float = 0.03  # h1 volume / MC below this = FAKE-MC
    thin_max_liq_to_mc: float = 0.03  # pool liquidity / MC below this = DÜNN (graduated tokens)
    fast: bool = False  # fewer transactions and wallet profiles for an earlier decision
    use_market: bool = True


@dataclass
class QuickReport:
    mint: str
    word: str
    phase: str  # curve | graduated | unknown
    score: float | None = None
    name: str | None = None
    symbol: str | None = None
    age_s: float | None = None
    mc_sol: float | None = None
    mc_usd: float | None = None
    volume_sol: float | None = None
    volume_usd: float | None = None
    volume_60s_sol: float | None = None
    turnover: float | None = None
    liquidity_sol: float | None = None
    liquidity_usd: float | None = None
    liq_to_mc: float | None = None
    progress: float | None = None
    holders: int | None = None
    holders_delta_60s: int | None = None
    buys: int | None = None
    sells: int | None = None
    net_flow_sol: float | None = None
    dev_share: float | None = None
    dev_sold: float | None = None
    bundle_share: float | None = None
    creator_prior: int | None = None
    creator_graduated: int | None = None
    creator_dead: int | None = None
    socials_text: str | None = None
    bots_share: float | None = None
    sol_usd: float | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    verdict: Verdict | None = None
    market: MarketData | None = None
    elapsed_s: float = 0.0

    @property
    def buy_signal(self) -> bool:
        return self.word == "GO"

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("verdict", "market")}
        d["verdict"] = self.verdict.to_dict() if self.verdict else None
        d["market"] = self.market.to_dict() if self.market else None
        return d


def word_for(verdict: Verdict | None, flags: list[str], phase: str) -> str:
    rug = any(f.split(" ")[0] in RUG_FLAGS for f in flags)
    if phase == "graduated":
        return "RUG" if rug else "GRAD"
    if verdict is None:
        return "?"
    label = verdict.label
    if label == LABEL_YES:
        return "WARTE" if go_blockers(flags) else "GO"
    if label == LABEL_NO:
        if rug:
            return "RUG"
        if any(f.startswith("STILL") for f in flags):
            return "TOT"
        return "NEIN"
    if label == LABEL_UNCLEAR:
        return "WARTE"
    if label == LABEL_TOO_EARLY:
        return "FRÜH"
    if label == LABEL_GRADUATED:
        return "GRAD"
    if label == LABEL_NO_DATA:
        return "?"
    return "?"


def _socials_text(feats: Features | None, market: MarketData | None) -> str | None:
    if feats is not None and feats.socials_count is not None:
        if feats.socials_count == 0:
            return "keine"
        return f"{feats.socials_count} Links"
    if market is not None and market.socials:
        return f"{market.socials} Links"
    return None


def market_flags(market: MarketData | None, phase: str, cfg: QuickConfig) -> list[str]:
    flags: list[str] = []
    if market is None:
        return flags
    mc = market.market_cap_usd or market.fdv_usd
    if mc and mc >= cfg.fake_mc_min_usd and market.volume_h1_usd is not None:
        turnover = market.volume_h1_usd / mc
        if turnover < cfg.fake_mc_max_turnover_h1:
            flags.append(f"FAKE-MC {turnover:.3f}")
    if phase == "graduated" and mc and market.liquidity_usd is not None and mc > 0:
        ratio = market.liquidity_usd / mc
        if ratio < cfg.thin_max_liq_to_mc:
            flags.append(f"DÜNN {ratio:.3f}")
    return flags


def report_from_features(
    mint: str,
    feats: Features,
    verdict: Verdict | None,
    cfg: ScoringConfig,
    market: MarketData | None = None,
    price: float | None = None,
    name: str | None = None,
    symbol: str | None = None,
    phase: str = "curve",
    quick: QuickConfig | None = None,
) -> QuickReport:
    """Fold on-chain features (and optional market data) into the numbers of a short message."""
    qc = quick or QuickConfig()
    r = QuickReport(mint=mint, word="?", phase=phase, name=name, symbol=symbol, verdict=verdict, market=market, sol_usd=price)
    r.age_s = feats.age_s
    r.score = verdict.score if verdict else None
    r.mc_sol = feats.mc_sol
    r.mc_usd = (feats.mc_sol * price) if (feats.mc_sol is not None and price) else (market.market_cap_usd if market else None)
    r.volume_sol = feats.volume_sol
    r.volume_usd = (feats.volume_sol * price) if (feats.volume_sol is not None and price) else (market.volume_h1_usd if market else None)
    r.volume_60s_sol = feats.volume_60s_sol
    r.turnover = feats.turnover
    r.liquidity_sol = feats.curve_sol
    r.liquidity_usd = (feats.curve_sol * price) if (feats.curve_sol is not None and price) else None
    r.liq_to_mc = feats.liq_to_mc
    r.progress = feats.progress
    r.holders = feats.holders_now
    if feats.holders_now_trades is not None and feats.holders_60s_ago is not None:
        r.holders_delta_60s = feats.holders_now_trades - feats.holders_60s_ago
    r.buys = feats.organic_buys_120s
    r.sells = feats.organic_sells_120s
    r.net_flow_sol = feats.organic_net_flow_120s_sol
    r.dev_share = feats.dev_buy_share
    r.dev_sold = feats.dev_sold_share
    r.bundle_share = feats.creation_window_share
    r.creator_prior = feats.creator_prior_tokens
    r.creator_graduated = feats.creator_graduated
    r.creator_dead = feats.creator_dead
    r.bots_share = feats.bot_buy_share
    r.socials_text = _socials_text(feats, market)
    if verdict is not None:
        r.notes = list(verdict.notes)
    flags = short_flags(feats, cfg)
    flags += [f for f in market_flags(market, phase, qc) if f.split(" ")[0] not in {x.split(" ")[0] for x in flags}]
    r.flags = flags
    r.word = word_for(verdict, flags, phase)
    if verdict is not None and verdict.label == LABEL_YES and r.word == "WARTE":
        r.notes.append("Score reicht für GO, aber Warnsignal: " + ", ".join(go_blockers(flags)))
    return r


def quick_check(
    mint: str,
    rpc: SolanaRpc,
    config: ScoringConfig | None = None,
    quick: QuickConfig | None = None,
    cache: ProfileCache | None = None,
    launch_hint: float | None = None,
    signatures: list[dict] | None = None,
    now: float | None = None,
) -> QuickReport:
    """Numbers, flags and a one-word verdict for one token. Raises RpcError when the RPC is unusable."""
    cfg = config or ScoringConfig()
    qc = quick or QuickConfig()
    when = now if now is not None else time.time()
    t0 = time.monotonic()
    report = QuickReport(mint=mint, word="?", phase="unknown")

    market_future = None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    if qc.use_market:
        market_future = pool.submit(fetch_market, mint)

    curve = None
    raw = rpc.get_account_data(derive_bonding_curve(mint))
    if raw:
        try:
            curve = decode_bonding_curve(raw)
        except BorshError:
            curve = None
    if curve is None:
        phase = "unknown"
    elif curve.complete:
        phase = "graduated"
    else:
        phase = "curve"

    feats: Features | None = None
    verdict: Verdict | None = None
    snap = None
    if phase == "curve":
        snap = collect(
            mint,
            rpc,
            max_tx=150 if qc.fast else 400,
            early_wallets=4 if qc.fast else 6,
            creator_scan_tx=40 if qc.fast else 80,
            cache=cache,
            launch_hint=launch_hint,
            now=when,
            signatures=signatures,
        )
        feats = compute_features(snap, when)
        verdict = score_features(feats, cfg)
        verdict.notes.extend(n for n in snap.notes if n not in verdict.notes)

    market: MarketData | None = None
    if market_future is not None:
        try:
            market = market_future.result(timeout=6.0)
        except Exception:  # noqa: BLE001 - market data is best effort
            market = None
    pool.shutdown(wait=False)
    price = sol_usd(market.sol_usd if market else None) if (feats is not None or market is not None) else None

    if feats is not None:
        name, symbol = (snap.create.name, snap.create.symbol) if (snap and snap.create) else (None, None)
        report = report_from_features(mint, feats, verdict, cfg, market, price, name, symbol, phase, qc)
    else:
        report.phase = phase
        report.sol_usd = price
        report.market = market
        if phase == "unknown":
            report.notes.append("keine pump.fun-Kurve gefunden; nur Marktzahlen")
        if market is not None:
            report.name, report.symbol = market.name, market.symbol
            if market.pair_created_at:
                report.age_s = max(0.0, when - market.pair_created_at)
            report.mc_usd = market.market_cap_usd or market.fdv_usd
            report.mc_sol = (report.mc_usd / price) if (report.mc_usd and price) else None
            report.volume_usd = market.volume_h1_usd
            report.volume_sol = (market.volume_h1_usd / price) if (market.volume_h1_usd is not None and price) else None
            if report.mc_usd and market.volume_h1_usd is not None:
                report.turnover = market.volume_h1_usd / report.mc_usd
            report.liquidity_usd = market.liquidity_usd
            report.liquidity_sol = market.liquidity_quote
            if report.mc_usd and market.liquidity_usd is not None:
                report.liq_to_mc = market.liquidity_usd / report.mc_usd
            report.buys = market.buys_h1 if market.buys_h1 is not None else market.buys_m5
            report.sells = market.sells_h1 if market.sells_h1 is not None else market.sells_m5
            if phase == "graduated":
                try:
                    das = rpc.das_get_token_accounts(mint)
                except RpcError:
                    das = None
                if das is not None:
                    report.holders = sum(1 for a in das if a["amount"] > 10**9)
        report.socials_text = _socials_text(None, market)
        report.flags = market_flags(market, phase, qc)
        report.word = word_for(None, report.flags, phase) if market is not None else "?"
    report.elapsed_s = time.monotonic() - t0
    return report
