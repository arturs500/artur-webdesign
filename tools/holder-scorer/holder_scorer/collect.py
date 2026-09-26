"""Collect everything the scorer needs about one pump.fun token.

One ``collect`` call performs:

1. bonding-curve account (state, creator, quote asset, graduated?)
2. the token's transaction history (trade + create events)
3. in parallel: holder list (Helius DAS, else the 20 largest accounts),
   the creator's other tokens and wallet profile, profiles of the first
   buyers, and the off-chain metadata JSON

The two mandatory calls (curve account, signature list) raise ``RpcError``
when the endpoint is unusable, so callers can tell "no data" from "RPC
broken". Every optional step records a note when it could not run, and the
features layer treats missing inputs as unknown rather than zero.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import requests

from .encoding import BorshError, TOKEN_2022_PROGRAM, TOKEN_PROGRAM
from .pump import (
    BondingCurveState,
    CreateEvent,
    TradeEvent,
    decode_bonding_curve,
    derive_bonding_curve,
    derive_curve_token_account,
    parse_transaction,
)
from .rpc import RpcError, SolanaRpc

IPFS_GATEWAYS = ("https://ipfs.io/ipfs/",)
HEAD_TX = 60  # oldest transactions always fetched (creation window, dev buy)
TAIL_WINDOW_S = 150  # newest transactions fetched by time window when history is truncated
YOUNG_TOKEN_S = 1800  # a creator's token launched within this many seconds is "young", not "dead"


@dataclass
class HolderInfo:
    owner: str
    amount: int
    account: str | None = None


@dataclass
class WalletProfile:
    address: str
    tx_count: int  # capped at the signature page size used
    first_seen: int | None = None  # unix time of first known tx (lower bound when capped)
    funder: str | None = None
    funder_busy: bool | None = None  # funder looks like an exchange hot wallet
    is_fresh: bool = False


@dataclass
class CreatorHistory:
    address: str
    prior_tokens: int = 0
    graduated: int = 0
    dead: int = 0
    active: int = 0
    young: int = 0
    source: str = "none"  # rpc | rpc(partial) | none
    coverage_note: str = ""
    scanned_tx: int = 0
    sample_capped: bool = False
    prev_launch_ts: int | None = None
    launches_in_scan: int = 0
    scan_span_s: float | None = None


class ProfileCache:
    """Thread-safe LRU cache for creator histories and wallet profiles across tokens."""

    def __init__(self, max_items: int = 4000, ttl_s: float = 1800.0):
        self.max_items = max_items
        self.ttl_s = ttl_s
        self._data: "OrderedDict[tuple[str, str], tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, kind: str, key: str) -> Any:
        with self._lock:
            item = self._data.get((kind, key))
            if item is None or item[0] < time.monotonic():
                self.misses += 1
                self._data.pop((kind, key), None)
                return None
            self._data.move_to_end((kind, key))
            self.hits += 1
            return item[1]

    def put(self, kind: str, key: str, value: Any) -> None:
        with self._lock:
            self._data[(kind, key)] = (time.monotonic() + self.ttl_s, value)
            self._data.move_to_end((kind, key))
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)


@dataclass
class Snapshot:
    mint: str
    bonding_curve: str
    collected_at: float
    curve: BondingCurveState | None = None
    create: CreateEvent | None = None
    trades: list[TradeEvent] = field(default_factory=list)
    total_signatures: int = 0
    failed_tx: int = 0
    missing_tx: int = 0
    sig_meta: list[tuple[int | None, bool]] = field(default_factory=list)  # (blockTime, failed) per signature
    history_ok: bool = False
    head_complete: bool = True  # the oldest transactions (creation) are in the fetched set
    partial_history: bool = False
    mayhem_vault: str | None = None
    launch_hint: float | None = None
    holders: list[HolderInfo] | None = None
    holders_source: str = "none"  # das | largest | trades | none
    metadata: dict[str, Any] = field(default_factory=dict)
    metadata_ok: bool = False
    creator_history: CreatorHistory | None = None
    creator_profile: WalletProfile | None = None
    early_wallets: list[WalletProfile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def dev_addresses(self) -> set[str]:
        devs: set[str] = set()
        if self.create:
            devs.update({self.create.user, self.create.creator})
        if self.curve and self.curve.creator:
            devs.add(self.curve.creator)
        return devs

    @property
    def history_complete(self) -> bool:
        return self.history_ok and not self.partial_history and self.head_complete


def derive_balances(trades: list[TradeEvent]) -> dict[str, int]:
    balances: dict[str, int] = {}
    for t in trades:
        delta = t.token_amount if t.is_buy else -t.token_amount
        balances[t.user] = balances.get(t.user, 0) + delta
    return balances


def _fetch_json(url: str, timeout: float = 6.0) -> dict[str, Any] | None:
    if url.startswith("ipfs://"):
        url = IPFS_GATEWAYS[0] + url[len("ipfs://") :]
    try:
        resp = requests.get(url, timeout=timeout, headers={"accept": "application/json"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (requests.RequestException, ValueError):
        return None


def _wallet_profile(
    rpc: SolanaRpc, address: str, launch_time: int | None, limit: int = 1000
) -> tuple[WalletProfile, str | None, list[dict[str, Any]]]:
    """Profile a wallet; returns the profile, its first tx signature (if known) and the signature page."""
    sigs = rpc.get_signatures(address, limit=limit)
    profile = WalletProfile(address=address, tx_count=len(sigs))
    first_sig = None
    capped = len(sigs) >= limit
    if sigs:
        oldest = sigs[-1]
        profile.first_seen = oldest.get("blockTime")
        if not capped:
            first_sig = oldest.get("signature")
    if launch_time and profile.first_seen and not capped:
        profile.is_fresh = profile.tx_count <= 25 and profile.first_seen >= launch_time - 86_400
    return profile, first_sig, sigs


def _fetch_history(snap: Snapshot, rpc: SolanaRpc, mint: str, max_tx: int, now: float) -> None:
    """Steps 2: signatures, transactions, events. Raises RpcError when the signature list is unavailable."""
    sigs = rpc.get_signatures(mint, limit=1000)
    pages = 1
    while sigs and len(sigs) >= 1000 * pages and pages < 3:
        more = rpc.get_signatures(mint, limit=1000, before=sigs[-1]["signature"])
        if not more:
            break
        sigs.extend(more)
        pages += 1
    snap.head_complete = len(sigs) < 1000 * pages
    if not snap.head_complete:
        snap.partial_history = True
        snap.notes.append(f"more than {len(sigs)} signatures; the creation transaction may be missing")
    snap.total_signatures = len(sigs)
    snap.sig_meta = [(s.get("blockTime"), s.get("err") is not None) for s in sigs]
    ok_sigs = [s for s in sigs if s.get("err") is None]
    snap.failed_tx = len(sigs) - len(ok_sigs)
    ok_sigs.reverse()  # oldest first
    if len(ok_sigs) > max_tx:
        head = ok_sigs[:HEAD_TX]
        cut = now - TAIL_WINDOW_S
        recent = [s for s in ok_sigs[HEAD_TX:] if (s.get("blockTime") or 0) >= cut]
        tail = recent[-(max_tx - HEAD_TX) :] if recent else ok_sigs[-(max_tx - HEAD_TX) :]
        selected = head + tail
        snap.partial_history = True
        note = f"history truncated: {len(ok_sigs)} successful txs, fetched {len(selected)}"
        if len(recent) > len(tail):
            note += f"; last {TAIL_WINDOW_S} s only partially covered"
        snap.notes.append(note)
    else:
        selected = ok_sigs
    signatures = [s["signature"] for s in selected]
    txs = rpc.get_transactions(signatures) if signatures else {}
    missing = [s for s in signatures if txs.get(s) is None]
    if missing:
        txs.update(rpc.get_transactions(missing))
        missing = [s for s in signatures if txs.get(s) is None]
    if missing:
        snap.missing_tx = len(missing)
        snap.partial_history = True
        snap.notes.append(f"{len(missing)} of {len(signatures)} transactions could not be fetched; bundle and dev values treated as unknown")
    snap.history_ok = not signatures or len(missing) < len(signatures)
    order = {sig: i for i, sig in enumerate(signatures)}
    trades: list[tuple[int, int, TradeEvent]] = []
    for sig in signatures:
        parsed = parse_transaction(sig, txs.get(sig))
        if parsed is None:
            continue
        for ce in parsed.creates:
            if ce.mint == mint and snap.create is None:
                snap.create = ce
                snap.mayhem_vault = parsed.mayhem_token_vault
        for tr in parsed.trades:
            if tr.mint == mint:
                trades.append((tr.slot, order[sig], tr))
    trades.sort(key=lambda x: (x[0], x[1]))
    snap.trades = [t[2] for t in trades]


def _fetch_holders(
    snap: Snapshot, rpc: SolanaRpc, mint: str, use_das: bool, allow_largest: bool = True
) -> tuple[list[HolderInfo] | None, str, list[str]]:
    """Step 3a. Returns (holders, source, notes). Without DAS, a complete trade history beats the top-20 list."""
    notes: list[str] = []
    curve_atas = {derive_curve_token_account(snap.bonding_curve, mint), derive_curve_token_account(snap.bonding_curve, mint, TOKEN_2022_PROGRAM)}
    if snap.mayhem_vault:
        curve_atas.add(snap.mayhem_vault)
    exclude_owners = {snap.bonding_curve}
    das = None
    if use_das:
        try:
            das = rpc.das_get_token_accounts(mint)
        except RpcError as exc:
            notes.append(f"DAS token accounts failed for this mint: {exc}")
    if das is not None:
        merged: dict[str, int] = {}
        for item in das:
            if item["owner"] in exclude_owners or item.get("address") in curve_atas:
                continue
            merged[item["owner"]] = merged.get(item["owner"], 0) + item["amount"]
        return [HolderInfo(o, a) for o, a in merged.items() if a > 0], "das", notes
    if not allow_largest:
        return None, "none", notes
    try:
        largest = rpc.get_token_largest_accounts(mint)
    except RpcError as exc:
        notes.append(f"largest accounts unavailable: {exc}")
        return None, "none", notes
    accounts = [(item["address"], int(item.get("amount", 0))) for item in largest if item.get("address") not in curve_atas and int(item.get("amount", 0)) > 0]
    owners: dict[str, str] = {}
    if accounts:
        try:
            owners = rpc.get_token_account_owners([a for a, _ in accounts])
        except RpcError as exc:
            notes.append(f"owner lookup for largest accounts failed: {exc}")
    merged = {}
    holders: list[HolderInfo] = []
    for addr, amount in accounts:
        owner = owners.get(addr, addr)
        if owner in exclude_owners:
            continue
        merged[owner] = merged.get(owner, 0) + amount
    holders = [HolderInfo(o, a) for o, a in merged.items()]
    notes.append("holder list limited to the 20 largest token accounts" + (" (endpoint has no DAS)" if rpc.das_supported is False else " (DAS unavailable for this mint)"))
    return holders, "largest", notes


def _creator_history(
    rpc: SolanaRpc, creator: str, mint: str, launch_time: int | None, scan_tx: int, cache: ProfileCache | None
) -> tuple[CreatorHistory, WalletProfile | None, str | None]:
    """Step 3b: the creator's other tokens plus the creator wallet profile and first-tx signature."""
    cached = cache.get("creator", creator) if cache else None
    if cached is not None:
        history, profile, first_sig = cached
        return history, profile, first_sig
    history = CreatorHistory(address=creator)
    profile, first_sig, sigs = _wallet_profile(rpc, creator, launch_time)
    history.sample_capped = len(sigs) >= 1000
    scan = [s for s in sigs if s.get("err") is None][:scan_tx]
    history.scanned_tx = len(scan)
    times = [s.get("blockTime") for s in scan if s.get("blockTime")]
    if len(times) >= 2:
        history.scan_span_s = float(max(times) - min(times))
    created: dict[str, int | None] = {}
    if scan:
        txs = rpc.get_transactions([s["signature"] for s in scan])
        for s in scan:
            parsed = parse_transaction(s["signature"], txs.get(s["signature"]))
            if not parsed:
                continue
            for m in parsed.created_mints:
                if m != mint and m not in created:
                    created[m] = parsed.block_time
        history.source = "rpc(partial)" if history.sample_capped else "rpc"
        history.coverage_note = f"last {len(scan)} creator transactions scanned"
    other_launches = [t for t in created.values() if t]
    history.launches_in_scan = len(created)
    if launch_time:
        before = [t for t in other_launches if t < launch_time]
        history.prev_launch_ts = max(before) if before else None
    if created:
        mints = list(created)[:300]
        datas = rpc.get_multiple_account_data([derive_bonding_curve(m) for m in mints])
        for m, data in zip(mints, datas):
            if not data:
                continue
            try:
                st = decode_bonding_curve(data)
            except BorshError:
                continue
            history.prior_tokens += 1
            ts = created.get(m)
            if st.complete:
                history.graduated += 1
            elif launch_time and ts and launch_time - ts < YOUNG_TOKEN_S:
                history.young += 1
            elif st.quote_is_sol and st.real_quote_reserves < 2 * 10**9:
                history.dead += 1
            else:
                history.active += 1
    if cache:
        cache.put("creator", creator, (history, profile, first_sig))
    return history, profile, first_sig


def _early_wallets(
    rpc: SolanaRpc, wallets: list[str], launch_time: int | None, cache: ProfileCache | None, creator: str | None, creator_first_sig: str | None
) -> tuple[list[WalletProfile], str | None, list[str]]:
    """Step 3c: profiles of the first buyers (fresh wallets, funders). Returns profiles, creator funder, notes."""
    notes: list[str] = []
    profiles: dict[str, WalletProfile] = {}
    first_sigs: dict[str, str] = {}
    todo = []
    for addr in wallets:
        cached = cache.get("wallet", addr) if cache else None
        if cached is not None:
            profiles[addr] = cached
        else:
            todo.append(addr)

    def load(addr: str) -> tuple[str, WalletProfile, str | None]:
        profile, first_sig, _ = _wallet_profile(rpc, addr, launch_time, limit=200)
        return addr, profile, first_sig

    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(todo))) as pool:
            for fut in concurrent.futures.as_completed([pool.submit(load, a) for a in todo]):
                try:
                    addr, profile, first_sig = fut.result()
                except RpcError as exc:
                    notes.append(f"wallet profile failed: {exc}")
                    continue
                profiles[addr] = profile
                if first_sig:
                    first_sigs[addr] = first_sig
    if creator and creator_first_sig:
        first_sigs[creator] = creator_first_sig
    creator_funder = None
    if first_sigs:
        addrs = list(first_sigs)
        ftxs = rpc.get_transactions([first_sigs[a] for a in addrs])
        for addr in addrs:
            parsed = parse_transaction(first_sigs[addr], ftxs.get(first_sigs[addr]))
            if parsed and parsed.fee_payer and parsed.fee_payer != addr:
                if addr in profiles:
                    profiles[addr].funder = parsed.fee_payer
                elif addr == creator:
                    creator_funder = parsed.fee_payer
    # A funder shared by several wallets may simply be an exchange hot wallet: check its activity once.
    funder_count: dict[str, int] = {}
    for p in profiles.values():
        if p.funder:
            funder_count[p.funder] = funder_count.get(p.funder, 0) + 1
    busy: dict[str, bool] = {}
    for funder, n in funder_count.items():
        if n < 2 or funder == creator or funder == creator_funder:
            continue
        cached = cache.get("busy", funder) if cache else None
        if cached is None:
            try:
                cached = len(rpc.get_signatures(funder, limit=50)) >= 50
            except RpcError:
                cached = None
            if cache and cached is not None:
                cache.put("busy", funder, cached)
        busy[funder] = bool(cached)
    for p in profiles.values():
        if p.funder in busy:
            p.funder_busy = busy[p.funder]
        if cache:
            cache.put("wallet", p.address, p)
    return [profiles[a] for a in wallets if a in profiles], creator_funder, notes


def collect(
    mint: str,
    rpc: SolanaRpc,
    *,
    max_tx: int = 400,
    early_wallets: int = 6,
    creator_scan_tx: int = 80,
    fetch_metadata: bool = True,
    deep: bool = True,
    use_das: bool = True,
    cache: ProfileCache | None = None,
    launch_hint: float | None = None,
    now: float | None = None,
) -> Snapshot:
    now = now if now is not None else time.time()
    t0 = time.monotonic()
    snap = Snapshot(mint=mint, bonding_curve=derive_bonding_curve(mint), collected_at=now, launch_hint=launch_hint)

    # 1. bonding curve (RpcError propagates: without an RPC nothing else makes sense) -----------
    raw = rpc.get_account_data(snap.bonding_curve)
    if raw:
        try:
            snap.curve = decode_bonding_curve(raw)
        except BorshError as exc:
            snap.notes.append(f"bonding curve not decodable: {exc}")
    else:
        snap.notes.append("bonding curve account not found (not a pump.fun token or not yet created)")
    snap.timings["curve"] = time.monotonic() - t0

    # 2. transaction history --------------------------------------------------------------------
    t1 = time.monotonic()
    _fetch_history(snap, rpc, mint, max_tx, now)
    snap.timings["history"] = time.monotonic() - t1
    if snap.total_signatures == 0:
        snap.timings["total"] = time.monotonic() - t0
        return snap

    creator = None
    if snap.create:
        creator = snap.create.creator or snap.create.user
    elif snap.curve and snap.curve.creator:
        creator = snap.curve.creator
    launch_time = snap.create.timestamp if snap.create else (int(launch_hint) if launch_hint else None)

    # 3. independent branches in parallel ------------------------------------------------------
    t2 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures: dict[str, concurrent.futures.Future] = {}
        futures["holders"] = pool.submit(_fetch_holders, snap, rpc, mint, use_das, not snap.history_complete)
        if fetch_metadata and snap.create and snap.create.uri:
            futures["metadata"] = pool.submit(_fetch_json, snap.create.uri)
        if creator:
            futures["creator"] = pool.submit(_creator_history, rpc, creator, mint, launch_time, creator_scan_tx, cache)
        early: list[str] = []
        if deep and snap.trades and snap.head_complete:
            devs = snap.dev_addresses
            for tr in snap.trades:
                if tr.is_buy and tr.user not in devs and tr.user not in early:
                    early.append(tr.user)
                if len(early) >= early_wallets:
                    break

        creator_first_sig = None
        try:
            if "creator" in futures:
                snap.creator_history, snap.creator_profile, creator_first_sig = futures["creator"].result()
        except RpcError as exc:
            snap.notes.append(f"creator scan failed: {exc}")
        snap.timings["creator"] = time.monotonic() - t2

        if early:
            futures["early"] = pool.submit(_early_wallets, rpc, early, launch_time, cache, creator, creator_first_sig)

        try:
            snap.holders, snap.holders_source, notes = futures["holders"].result()
            snap.notes.extend(notes)
        except RpcError as exc:
            snap.notes.append(f"holder lookup failed: {exc}")
        snap.timings["holders"] = time.monotonic() - t2

        if "early" in futures:
            try:
                snap.early_wallets, creator_funder, notes = futures["early"].result()
                snap.notes.extend(notes)
                if creator_funder and snap.creator_profile:
                    snap.creator_profile.funder = creator_funder
            except RpcError as exc:
                snap.notes.append(f"early wallet profiles failed: {exc}")
        snap.timings["early_wallets"] = time.monotonic() - t2

        if "metadata" in futures:
            try:
                data = futures["metadata"].result(timeout=8.0)
            except Exception:  # noqa: BLE001 - metadata is best effort
                data = None
            if data:
                snap.metadata = data
                snap.metadata_ok = True
            else:
                snap.notes.append("metadata JSON could not be fetched")
        snap.timings["metadata"] = time.monotonic() - t2

    # holders derived from trades only when nothing better exists and the history is complete
    if snap.holders is None and snap.history_complete:
        balances = derive_balances(snap.trades)
        snap.holders = [HolderInfo(o, a) for o, a in balances.items() if a > 0]
        snap.holders_source = "trades"
    elif snap.holders is None:
        snap.notes.append("holder count unknown (no holder endpoint and incomplete trade history)")
    snap.timings["total"] = time.monotonic() - t0
    return snap
