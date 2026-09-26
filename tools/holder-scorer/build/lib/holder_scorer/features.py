"""Turn a ``Snapshot`` into the numeric factors the scorer works with.

Every field is either a number, a bool, or ``None`` when the underlying data
was not available. The scorer treats ``None`` as "unknown" and never as zero.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass

from .collect import Snapshot
from .pump import LAMPORTS_PER_SOL, TOKEN_TOTAL_SUPPLY, TradeEvent

DUST_TOKENS = 1_000 * 10**6  # ignore balances below 1000 tokens (of 1 billion)


@dataclass
class Features:
    mint: str
    collected_at: float
    age_s: float | None
    n_trades: int
    n_buys: int
    n_sells: int
    unique_buyers: int
    unique_traders: int
    failed_tx_share: float | None
    # holders and momentum
    holders_now: int | None
    holders_source: str
    holders_60s_ago: int | None
    holders_120s_ago: int | None
    holder_growth_60s: float | None
    new_buyers_60s: int
    new_buyers_120s: int
    buys_60s: int
    sells_60s: int
    buys_120s: int
    sells_120s: int
    buy_sell_ratio_120s: float | None
    net_flow_120s_sol: float | None
    seconds_since_last_trade: float | None
    # curve
    complete: bool | None
    progress: float | None
    curve_sol: float | None
    quote_is_sol: bool
    # distribution
    top10_share: float | None
    largest_holder_share: float | None
    creation_slot_buyers: int | None
    creation_window_share: float | None
    dev_buy_share: float | None
    dev_sold_share: float | None
    dev_holds_share: float | None
    # early wallets
    early_wallets_checked: int
    early_fresh_wallets: int
    early_shared_funder_max: int
    early_funded_by_creator: int
    # creator
    creator_prior_tokens: int | None
    creator_graduated: int | None
    creator_dead: int | None
    creator_history_source: str
    creator_wallet_tx_count: int | None
    creator_wallet_age_s: float | None
    creator_is_fresh: bool | None
    # metadata
    metadata_ok: bool
    socials_count: int | None
    has_image: bool | None
    # trade shape
    median_buy_sol: float | None
    small_buy_share: float | None
    wash_share: float | None
    partial_history: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _holders_at(trades: list[TradeEvent], until_ts: float) -> int:
    balances: dict[str, int] = {}
    for t in trades:
        ts = t.timestamp or t.block_time or 0
        if ts > until_ts:
            break
        delta = t.token_amount if t.is_buy else -t.token_amount
        balances[t.user] = balances.get(t.user, 0) + delta
    return sum(1 for v in balances.values() if v > DUST_TOKENS)


def _social_link_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip().lower()
    if len(v) < 8 or not v.startswith("http"):
        return False
    stripped = v.split("://", 1)[1].rstrip("/")
    # a bare domain such as https://x.com or https://t.me is not a real link
    return "/" in stripped


def compute_features(snap: Snapshot, now: float | None = None) -> Features:
    now = now if now is not None else time.time()
    trades = snap.trades
    devs = snap.dev_addresses
    ts_of = lambda t: (t.timestamp or t.block_time or 0)  # noqa: E731

    launch_ts = snap.create.timestamp if snap.create else (ts_of(trades[0]) if trades else None)
    age = (now - launch_ts) if launch_ts else None

    buys = [t for t in trades if t.is_buy]
    sells = [t for t in trades if not t.is_buy]
    buyers_order: list[str] = []
    seen_buyers: set[str] = set()
    for t in buys:
        if t.user not in seen_buyers:
            seen_buyers.add(t.user)
            buyers_order.append(t.user)
    traders = {t.user for t in trades}

    def window(seconds: float) -> list[TradeEvent]:
        return [t for t in trades if ts_of(t) >= now - seconds]

    w60, w120 = window(60), window(120)

    def new_buyers_since(seconds: float) -> int:
        start = now - seconds
        before: set[str] = {t.user for t in buys if ts_of(t) < start}
        return len({t.user for t in buys if ts_of(t) >= start and t.user not in before})

    buys_60 = sum(1 for t in w60 if t.is_buy)
    sells_60 = len(w60) - buys_60
    buys_120 = sum(1 for t in w120 if t.is_buy)
    sells_120 = len(w120) - buys_120
    ratio_120 = (buys_120 / sells_120) if sells_120 else (float(buys_120) if buys_120 else None)
    net_flow_120 = sum((t.quote_lamports if t.is_buy else -t.quote_lamports) for t in w120) / LAMPORTS_PER_SOL if w120 else None
    last_trade_gap = (now - ts_of(trades[-1])) if trades else None

    # holders now: prefer the fetched list, but never trust a truncated "largest" list as a count
    holders_now: int | None
    if snap.holders is not None and snap.holders_source in ("das", "trades"):
        holders_now = sum(1 for h in snap.holders if h.amount > DUST_TOKENS)
    elif trades:
        holders_now = _holders_at(trades, now)
    else:
        holders_now = None
    holders_60 = _holders_at(trades, now - 60) if trades and not snap.partial_history else None
    holders_120 = _holders_at(trades, now - 120) if trades and not snap.partial_history else None
    if holders_now is not None and holders_60 is not None and (age is None or age >= 75):
        growth_60 = (holders_now - holders_60) / max(holders_60, 5)
    else:
        growth_60 = None

    # distribution ------------------------------------------------------------
    supply = snap.curve.token_total_supply if snap.curve else TOKEN_TOTAL_SUPPLY
    top10 = largest = None
    if snap.holders:
        amounts = sorted((h.amount for h in snap.holders), reverse=True)
        top10 = sum(amounts[:10]) / supply
        largest = amounts[0] / supply
    creation_slot_buyers = creation_window_share = None
    if snap.create and trades and not snap.partial_history:
        slot0 = snap.create.slot
        early = [t for t in buys if t.slot <= slot0 + 1 and t.user not in devs]
        creation_slot_buyers = len({t.user for t in early})
        creation_window_share = sum(t.token_amount for t in early) / supply
    dev_buy_share = dev_sold_share = dev_holds_share = None
    if trades and devs and not snap.partial_history:
        dev_bought = sum(t.token_amount for t in buys if t.user in devs)
        dev_sold = sum(t.token_amount for t in sells if t.user in devs)
        dev_buy_share = dev_bought / supply
        dev_sold_share = (dev_sold / dev_bought) if dev_bought else 0.0
        dev_holds_share = max(0, dev_bought - dev_sold) / supply

    # early wallets ---------------------------------------------------------------
    fresh = sum(1 for w in snap.early_wallets if w.is_fresh)
    funders: dict[str, int] = {}
    funded_by_creator = 0
    creator_addr = snap.creator_history.address if snap.creator_history else None
    creator_funder = snap.creator_profile.funder if snap.creator_profile else None
    for w in snap.early_wallets:
        if w.funder:
            funders[w.funder] = funders.get(w.funder, 0) + 1
            if w.funder == creator_addr or (creator_funder and w.funder == creator_funder):
                funded_by_creator += 1
    shared_max = max(funders.values()) if funders else 0

    # creator --------------------------------------------------------------------
    ch = snap.creator_history
    cp = snap.creator_profile
    creator_age = (launch_ts - cp.first_seen) if (cp and cp.first_seen and launch_ts) else None
    creator_fresh = cp.is_fresh if cp else None

    # metadata --------------------------------------------------------------------
    socials = has_image = None
    if snap.metadata_ok:
        md = snap.metadata
        socials = sum(1 for k in ("twitter", "telegram", "website") if _social_link_ok(md.get(k)))
        has_image = isinstance(md.get("image"), str) and md["image"].startswith(("http", "ipfs"))

    # trade shape -----------------------------------------------------------------
    quote_is_sol = snap.curve.quote_is_sol if snap.curve else True
    buy_sizes = [t.quote_lamports / LAMPORTS_PER_SOL for t in buys if t.user not in devs]
    median_buy = statistics.median(buy_sizes) if buy_sizes else None
    small_share = (sum(1 for s in buy_sizes if s < 0.1) / len(buy_sizes)) if buy_sizes else None
    per_wallet: dict[str, list[int]] = {}
    for t in trades:
        counts = per_wallet.setdefault(t.user, [0, 0])
        counts[0 if t.is_buy else 1] += 1
    washers = sum(1 for b, s in per_wallet.values() if b >= 3 and s >= 3)
    wash_share = (washers / len(per_wallet)) if per_wallet else None

    total_sigs = snap.total_signatures
    failed_share = (snap.failed_tx / total_sigs) if total_sigs else None

    return Features(
        mint=snap.mint,
        collected_at=snap.collected_at,
        age_s=age,
        n_trades=len(trades),
        n_buys=len(buys),
        n_sells=len(sells),
        unique_buyers=len(buyers_order),
        unique_traders=len(traders),
        failed_tx_share=failed_share,
        holders_now=holders_now,
        holders_source=snap.holders_source,
        holders_60s_ago=holders_60,
        holders_120s_ago=holders_120,
        holder_growth_60s=growth_60,
        new_buyers_60s=new_buyers_since(60),
        new_buyers_120s=new_buyers_since(120),
        buys_60s=buys_60,
        sells_60s=sells_60,
        buys_120s=buys_120,
        sells_120s=sells_120,
        buy_sell_ratio_120s=ratio_120,
        net_flow_120s_sol=net_flow_120,
        seconds_since_last_trade=last_trade_gap,
        complete=snap.curve.complete if snap.curve else None,
        progress=snap.curve.progress if snap.curve else None,
        curve_sol=(snap.curve.real_quote_reserves / LAMPORTS_PER_SOL) if snap.curve else None,
        quote_is_sol=quote_is_sol,
        top10_share=top10,
        largest_holder_share=largest,
        creation_slot_buyers=creation_slot_buyers,
        creation_window_share=creation_window_share,
        dev_buy_share=dev_buy_share,
        dev_sold_share=dev_sold_share,
        dev_holds_share=dev_holds_share,
        early_wallets_checked=len(snap.early_wallets),
        early_fresh_wallets=fresh,
        early_shared_funder_max=shared_max,
        early_funded_by_creator=funded_by_creator,
        creator_prior_tokens=ch.prior_tokens if ch and ch.source != "none" else None,
        creator_graduated=ch.graduated if ch and ch.source != "none" else None,
        creator_dead=ch.dead if ch and ch.source != "none" else None,
        creator_history_source=ch.source if ch else "none",
        creator_wallet_tx_count=cp.tx_count if cp else None,
        creator_wallet_age_s=creator_age,
        creator_is_fresh=creator_fresh,
        metadata_ok=snap.metadata_ok,
        socials_count=socials,
        has_image=has_image,
        median_buy_sol=median_buy if quote_is_sol else None,
        small_buy_share=small_share if quote_is_sol else None,
        wash_share=wash_share,
        partial_history=snap.partial_history,
    )
