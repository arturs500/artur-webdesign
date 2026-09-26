"""Turn a ``Snapshot`` into the numeric factors the scorer works with.

Every field is either a number, a bool, or ``None`` when the underlying data
was not available. The scorer treats ``None`` as "unknown" and never as zero.

Cohorts used below:

* devs: the creator / first-buyer addresses of the coin
* creation-window wallets: non-dev wallets that bought within the first
  ``CREATION_WINDOW_SLOTS`` slots after the create transaction (bundles, snipers)
* early cohort: creation-window wallets plus the first ten non-dev buyers
* bot wallets: wallets that repeat the same buy size three or more times, or
  buy and sell three or more times each (bump and wash bots)
* outside buyers: non-dev, non-bot buyers, the closest thing to organic demand
"""
from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass

from .collect import Snapshot, derive_balances
from .pump import INITIAL_REAL_TOKEN_RESERVES, LAMPORTS_PER_SOL, TOKEN_TOTAL_SUPPLY, TradeEvent

DUST_TOKENS = 1_000 * 10**6  # ignore balances below 1000 tokens (of 1 billion)
CREATION_WINDOW_SLOTS = 4  # about 1.25 s at 250 ms slots (since September 2026)
EARLY_COHORT_BUYERS = 10
REPEAT_BUYS = 3
QUOTE_ROUND = 10**6  # 0.001 SOL buckets for "same size" detection


@dataclass
class Features:
    mint: str
    collected_at: float
    age_s: float | None
    age_source: str
    n_trades: int
    n_buys: int
    n_sells: int
    unique_buyers: int
    unique_traders: int
    unique_outside_buyers: int
    failed_tx_share: float | None
    failed_after_30s_share: float | None
    # holders and momentum
    holders_now: int | None
    holders_source: str
    holders_listed: int | None
    holders_now_trades: int | None
    holders_60s_ago: int | None
    holders_120s_ago: int | None
    holder_growth_60s: float | None
    new_buyers_60s: int
    new_buyers_120s: int
    new_buyers_60s_raw: int
    outside_buyers_120s: int
    outside_buys_120s: int
    buys_60s: int
    sells_60s: int
    buys_120s: int
    sells_120s: int
    buy_sell_ratio_120s: float | None
    net_flow_120s_sol: float | None
    organic_buys_120s: int
    organic_sells_120s: int
    organic_buy_wallets_120s: int
    organic_sell_wallets_120s: int
    organic_net_flow_120s_sol: float | None
    seconds_since_last_trade: float | None
    price_change_60s: float | None
    # curve
    complete: bool | None
    progress: float | None
    curve_sol: float | None
    quote_is_sol: bool
    is_mayhem: bool | None
    is_holder_reward: bool | None
    # distribution
    top10_share: float | None
    largest_holder_share: float | None
    largest_float_share: float | None
    top3_float_share: float | None
    creation_slot_buyers: int | None
    creation_window_share: float | None
    creation_window_held_share: float | None
    creation_window_sold_share: float | None
    early_sold_share: float | None
    early_overhang: float | None
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
    creator_young: int | None
    creator_history_source: str
    creator_sample_capped: bool
    creator_wallet_tx_count: int | None
    creator_wallet_age_s: float | None
    creator_is_fresh: bool | None
    creator_seconds_since_prev_launch: float | None
    creator_launch_rate_per_h: float | None
    # metadata
    metadata_ok: bool
    socials_count: int | None
    has_image: bool | None
    # trade shape
    median_buy_sol: float | None
    small_buy_share: float | None
    wash_share: float | None
    repeat_wallet_share: float | None
    bot_buy_share: float | None
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
    if "://" not in v:
        return False
    scheme, rest = v.split("://", 1)
    if scheme not in ("http", "https"):
        return False
    rest = rest.rstrip("/")
    # a bare domain such as https://x.com or https://t.me is not a real link
    return "/" in rest and len(rest) > 3


def _bot_wallets(trades: list[TradeEvent], devs: set[str]) -> tuple[set[str], set[str], int]:
    """Return (bot wallets, wash wallets, wallets with any trade) excluding devs."""
    per_wallet: dict[str, list[TradeEvent]] = {}
    for t in trades:
        if t.user in devs:
            continue
        per_wallet.setdefault(t.user, []).append(t)
    repeat: set[str] = set()
    wash: set[str] = set()
    for user, ts in per_wallet.items():
        buys = [t for t in ts if t.is_buy]
        sells = len(ts) - len(buys)
        if len(buys) >= REPEAT_BUYS and sells >= REPEAT_BUYS:
            wash.add(user)
        if len(buys) >= REPEAT_BUYS:
            sizes: dict[int, int] = {}
            tokens: dict[int, int] = {}
            for t in buys:
                q = t.quote_lamports // QUOTE_ROUND
                sizes[q] = sizes.get(q, 0) + 1
                tokens[t.token_amount] = tokens.get(t.token_amount, 0) + 1
            if max(sizes.values()) >= REPEAT_BUYS or max(tokens.values()) >= REPEAT_BUYS:
                repeat.add(user)
    return repeat | wash, wash, len(per_wallet)


def compute_features(snap: Snapshot, now: float | None = None) -> Features:
    now = now if now is not None else time.time()
    trades = snap.trades
    devs = snap.dev_addresses
    ts_of = lambda t: (t.timestamp or t.block_time or 0)  # noqa: E731
    complete_history = snap.history_complete

    # age -------------------------------------------------------------------------
    if snap.create:
        launch_ts, age_source = float(snap.create.timestamp), "create"
    elif snap.launch_hint:
        launch_ts, age_source = float(snap.launch_hint), "hint"
    elif trades and snap.head_complete:
        launch_ts, age_source = float(ts_of(trades[0])), "first_trade"
    else:
        launch_ts, age_source = None, "unknown"
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
    bots, washers, nondev_wallets = _bot_wallets(trades, devs)
    outside = lambda u: u not in devs and u not in bots  # noqa: E731

    slot0 = snap.create.slot if snap.create else None
    # the creation window and the dev buy only need the head of the history, not the whole of it
    head_usable = snap.head_usable and (snap.head_last_slot is None or slot0 is None or snap.head_last_slot > slot0 + CREATION_WINDOW_SLOTS)
    das_balances = {h.owner: h.amount for h in snap.holders} if (snap.holders is not None and snap.holders_source == "das") else None
    window_wallets: set[str] = set()
    if slot0 is not None and head_usable:
        window_wallets = {t.user for t in buys if t.slot <= slot0 + CREATION_WINDOW_SLOTS and t.user not in devs}
    first_nondev = [u for u in buyers_order if u not in devs][:EARLY_COHORT_BUYERS]
    cohort = set(window_wallets) | set(first_nondev)

    def window(seconds: float) -> list[TradeEvent]:
        return [t for t in trades if ts_of(t) >= now - seconds]

    w60, w120 = window(60), window(120)

    def new_buyers_since(seconds: float, filt) -> int:
        start = now - seconds
        before: set[str] = {t.user for t in buys if ts_of(t) < start}
        return len({t.user for t in buys if ts_of(t) >= start and t.user not in before and filt(t.user)})

    buys_60 = sum(1 for t in w60 if t.is_buy)
    sells_60 = len(w60) - buys_60
    buys_120 = sum(1 for t in w120 if t.is_buy)
    sells_120 = len(w120) - buys_120
    ratio_120 = (buys_120 / sells_120) if sells_120 else (float(buys_120) if buys_120 else None)
    quote_is_sol = snap.curve.quote_is_sol if snap.curve else (trades[0].quote_is_sol if trades else True)
    net_flow_120 = None
    if w120 and quote_is_sol:
        net_flow_120 = sum((t.quote_lamports if t.is_buy else -t.quote_lamports) for t in w120) / LAMPORTS_PER_SOL
    organic_120 = [t for t in w120 if t.user not in devs and t.user not in window_wallets and t.user not in bots]
    organic_buys = [t for t in organic_120 if t.is_buy]
    organic_sells = [t for t in organic_120 if not t.is_buy]
    organic_net = None
    if organic_120 and quote_is_sol:
        organic_net = sum((t.quote_lamports if t.is_buy else -t.quote_lamports) for t in organic_120) / LAMPORTS_PER_SOL
    outside_buyers_120 = len({t.user for t in w120 if t.is_buy and outside(t.user)})
    outside_buys_120 = sum(1 for t in w120 if t.is_buy and outside(t.user))
    last_trade_gap = (now - ts_of(trades[-1])) if trades else None

    # price move without holders (self-pump) -----------------------------------------
    price_change = None
    if trades:
        last = trades[-1].price_after
        older = [t for t in trades if ts_of(t) <= now - 60]
        prev = older[-1].price_after if older else None
        if last and prev:
            price_change = last / prev - 1.0

    # holders ----------------------------------------------------------------------------
    holders_usable = snap.holders is not None and (snap.holders_source in ("das", "largest") or (snap.holders_source == "trades" and complete_history))
    holders_now: int | None = None
    if snap.holders is not None and snap.holders_source == "das":
        holders_now = sum(1 for h in snap.holders if h.amount > DUST_TOKENS)
    elif snap.holders is not None and snap.holders_source == "trades" and complete_history:
        holders_now = sum(1 for h in snap.holders if h.amount > DUST_TOKENS)
    holders_now_trades = _holders_at(trades, now) if trades and complete_history else None
    if holders_now is None and holders_now_trades is not None:
        holders_now = holders_now_trades
    holders_60 = _holders_at(trades, now - 60) if trades and complete_history else None
    holders_120 = _holders_at(trades, now - 120) if trades and complete_history else None
    growth_60 = None
    if holders_now_trades is not None and holders_60 is not None and (age is None or age >= 75):
        growth_60 = (holders_now_trades - holders_60) / max(holders_60, 5)

    # distribution -----------------------------------------------------------------------
    supply = snap.curve.token_total_supply if snap.curve and snap.curve.token_total_supply else TOKEN_TOTAL_SUPPLY
    top10 = largest = largest_float = top3_float = None
    balances = derive_balances(trades) if trades else {}
    circulating = sum(v for v in balances.values() if v > 0)
    float_tokens = None
    if snap.curve and snap.create and snap.create.real_token_reserves:
        float_tokens = snap.create.real_token_reserves - snap.curve.real_token_reserves
    elif snap.curve:
        float_tokens = INITIAL_REAL_TOKEN_RESERVES - snap.curve.real_token_reserves
    if not float_tokens or float_tokens <= 0:
        float_tokens = circulating or None
    if holders_usable and snap.holders:
        amounts = sorted((h.amount for h in snap.holders), reverse=True)
        top10 = sum(amounts[:10]) / supply
        largest = amounts[0] / supply
        nondev = sorted((h.amount for h in snap.holders if h.owner not in devs), reverse=True)
        if nondev and float_tokens:
            largest_float = min(1.0, nondev[0] / float_tokens)
            top3_float = min(1.0, sum(nondev[:3]) / float_tokens)
    creation_slot_buyers = creation_window_share = window_held = window_sold = None
    early_sold_share = early_overhang = None
    if slot0 is not None and head_usable:
        early_buys = [t for t in buys if t.user in window_wallets]
        creation_slot_buyers = len(window_wallets)
        bought = sum(t.token_amount for t in early_buys)
        creation_window_share = bought / supply
        # what the window wallets still hold: DAS is authoritative, a complete trade replay is second best
        held_map = das_balances if das_balances is not None else (balances if complete_history else None)
        if held_map is not None:
            held = sum(max(0, held_map.get(u, 0)) for u in window_wallets)
            window_held = held / supply
            window_sold = (1.0 - held / bought) if bought else None
        cohort_bought = sum(t.token_amount for t in buys if t.user in cohort)
        if complete_history:
            cohort_sold = sum(t.token_amount for t in sells if t.user in cohort)
        elif das_balances is not None:
            cohort_sold = max(0, cohort_bought - sum(max(0, das_balances.get(u, 0)) for u in cohort))
        else:
            cohort_sold = None
        if cohort_sold is not None:
            early_sold_share = (cohort_sold / cohort_bought) if cohort_bought else None
            if circulating > 0 and complete_history:
                early_overhang = max(0, cohort_bought - cohort_sold) / circulating
    dev_buy_share = dev_sold_share = dev_holds_share = None
    if trades and devs and head_usable:
        dev_bought = sum(t.token_amount for t in buys if t.user in devs)
        dev_buy_share = dev_bought / supply
        if complete_history:
            dev_sold = sum(t.token_amount for t in sells if t.user in devs)
            dev_sold_share = (dev_sold / dev_bought) if dev_bought else 0.0
            dev_holds_share = (sum(a for o, a in das_balances.items() if o in devs) / supply) if das_balances is not None else max(0, dev_bought - dev_sold) / supply
        elif das_balances is not None:
            dev_holds = sum(a for o, a in das_balances.items() if o in devs)
            dev_holds_share = dev_holds / supply
            dev_sold_share = max(0.0, 1.0 - dev_holds / dev_bought) if dev_bought else 0.0

    # early wallets ----------------------------------------------------------------------
    fresh = sum(1 for w in snap.early_wallets if w.is_fresh)
    funders: dict[str, int] = {}
    funded_by_creator = 0
    creator_addr = snap.creator_history.address if snap.creator_history else None
    creator_funder = snap.creator_profile.funder if snap.creator_profile else None
    for w in snap.early_wallets:
        if not w.funder:
            continue
        if w.funder == creator_addr or (creator_funder and w.funder == creator_funder):
            funded_by_creator += 1
        elif not w.funder_busy:
            funders[w.funder] = funders.get(w.funder, 0) + 1
    shared_max = max(funders.values()) if funders else 0

    # creator ------------------------------------------------------------------------------
    ch = snap.creator_history
    cp = snap.creator_profile
    creator_age = (launch_ts - cp.first_seen) if (cp and cp.first_seen and launch_ts) else None
    creator_known = ch is not None and ch.source != "none"
    since_prev = (launch_ts - ch.prev_launch_ts) if (ch and ch.prev_launch_ts and launch_ts) else None
    launch_rate = None
    if ch and ch.scan_span_s and ch.scanned_tx >= 5:
        launch_rate = ch.launches_in_scan / max(ch.scan_span_s / 3600.0, 0.25)

    # metadata --------------------------------------------------------------------------------
    socials = has_image = None
    if snap.metadata_ok:
        md = snap.metadata
        socials = sum(1 for k in ("twitter", "telegram", "website") if _social_link_ok(md.get(k)))
        img = md.get("image")
        has_image = isinstance(img, str) and img.startswith(("http", "ipfs"))

    # trade shape ---------------------------------------------------------------------------------
    outside_buy_sizes = [t.quote_lamports / LAMPORTS_PER_SOL for t in buys if outside(t.user)]
    median_buy = statistics.median(outside_buy_sizes) if outside_buy_sizes else None
    small_share = (sum(1 for s in outside_buy_sizes if s < 0.1) / len(outside_buy_sizes)) if outside_buy_sizes else None
    wash_share = (len(washers) / nondev_wallets) if nondev_wallets else None
    repeat_share = (len(bots) / nondev_wallets) if nondev_wallets else None
    nondev_buys = [t for t in buys if t.user not in devs]
    bot_buy_share = (sum(1 for t in nondev_buys if t.user in bots) / len(nondev_buys)) if nondev_buys else None

    total_sigs = snap.total_signatures
    failed_share = (snap.failed_tx / total_sigs) if total_sigs else None
    failed_after_30 = None
    if launch_ts and snap.sig_meta:
        late = [(bt, failed) for bt, failed in snap.sig_meta if bt and bt >= launch_ts + 30]
        if late:
            failed_after_30 = sum(1 for _, failed in late if failed) / len(late)

    progress = None
    if snap.curve:
        progress = snap.curve.progress_from(snap.create.real_token_reserves) if (snap.create and snap.create.real_token_reserves) else snap.curve.progress

    return Features(
        mint=snap.mint,
        collected_at=snap.collected_at,
        age_s=age,
        age_source=age_source,
        n_trades=len(trades),
        n_buys=len(buys),
        n_sells=len(sells),
        unique_buyers=len(buyers_order),
        unique_traders=len(traders),
        unique_outside_buyers=sum(1 for u in buyers_order if outside(u)),
        failed_tx_share=failed_share,
        failed_after_30s_share=failed_after_30,
        holders_now=holders_now,
        holders_source=snap.holders_source,
        holders_listed=len(snap.holders) if snap.holders is not None else None,
        holders_now_trades=holders_now_trades,
        holders_60s_ago=holders_60,
        holders_120s_ago=holders_120,
        holder_growth_60s=growth_60,
        new_buyers_60s=new_buyers_since(60, outside),
        new_buyers_120s=new_buyers_since(120, outside),
        new_buyers_60s_raw=new_buyers_since(60, lambda u: True),
        outside_buyers_120s=outside_buyers_120,
        outside_buys_120s=outside_buys_120,
        buys_60s=buys_60,
        sells_60s=sells_60,
        buys_120s=buys_120,
        sells_120s=sells_120,
        buy_sell_ratio_120s=ratio_120,
        net_flow_120s_sol=net_flow_120,
        organic_buys_120s=len(organic_buys),
        organic_sells_120s=len(organic_sells),
        organic_buy_wallets_120s=len({t.user for t in organic_buys}),
        organic_sell_wallets_120s=len({t.user for t in organic_sells}),
        organic_net_flow_120s_sol=organic_net,
        seconds_since_last_trade=last_trade_gap,
        price_change_60s=price_change,
        complete=snap.curve.complete if snap.curve else None,
        progress=progress,
        curve_sol=(snap.curve.real_quote_reserves / LAMPORTS_PER_SOL) if (snap.curve and quote_is_sol) else None,
        quote_is_sol=quote_is_sol,
        is_mayhem=(snap.curve.is_mayhem_mode if snap.curve and snap.curve.is_mayhem_mode is not None else (snap.create.is_mayhem_mode if snap.create else None)),
        is_holder_reward=snap.curve.is_holder_reward if snap.curve else None,
        top10_share=top10,
        largest_holder_share=largest,
        largest_float_share=largest_float,
        top3_float_share=top3_float,
        creation_slot_buyers=creation_slot_buyers,
        creation_window_share=creation_window_share,
        creation_window_held_share=window_held,
        creation_window_sold_share=window_sold,
        early_sold_share=early_sold_share,
        early_overhang=early_overhang,
        dev_buy_share=dev_buy_share,
        dev_sold_share=dev_sold_share,
        dev_holds_share=dev_holds_share,
        early_wallets_checked=len(snap.early_wallets),
        early_fresh_wallets=fresh,
        early_shared_funder_max=shared_max,
        early_funded_by_creator=funded_by_creator,
        creator_prior_tokens=ch.prior_tokens if creator_known else None,
        creator_graduated=ch.graduated if creator_known else None,
        creator_dead=ch.dead if creator_known else None,
        creator_young=ch.young if creator_known else None,
        creator_history_source=ch.source if ch else "none",
        creator_sample_capped=bool(ch and ch.sample_capped),
        creator_wallet_tx_count=cp.tx_count if cp else None,
        creator_wallet_age_s=creator_age,
        creator_is_fresh=cp.is_fresh if cp else None,
        creator_seconds_since_prev_launch=since_prev,
        creator_launch_rate_per_h=launch_rate,
        metadata_ok=snap.metadata_ok,
        socials_count=socials,
        has_image=has_image,
        median_buy_sol=median_buy if quote_is_sol else None,
        small_buy_share=small_share if quote_is_sol else None,
        wash_share=wash_share,
        repeat_wallet_share=repeat_share,
        bot_buy_share=bot_buy_share,
        partial_history=snap.partial_history,
    )
