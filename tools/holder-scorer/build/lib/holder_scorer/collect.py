"""Collect everything the scorer needs about one pump.fun token.

One ``collect`` call performs, in order:

1. bonding-curve account (state, creator, quote asset, graduated?)
2. the token's transaction history (trade + create events)
3. holder list (Helius DAS, else largest accounts, else derived from trades)
4. off-chain metadata (socials, image)
5. the creator's other tokens and wallet profile
6. profiles of the first buyers (fresh wallets, shared funders)

Every step is optional and records a note when it could not run, so the
scorer can treat missing inputs as "unknown" instead of guessing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .encoding import BorshError, TOKEN_2022_PROGRAM, TOKEN_PROGRAM, b58decode
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


@dataclass
class HolderInfo:
    owner: str
    amount: int


@dataclass
class WalletProfile:
    address: str
    tx_count: int  # capped at 1000
    first_seen: int | None = None  # unix time of first known tx (lower bound when capped)
    funder: str | None = None
    is_fresh: bool = False


@dataclass
class CreatorHistory:
    address: str
    prior_tokens: int = 0
    graduated: int = 0
    dead: int = 0
    active: int = 0
    source: str = "none"  # das | rpc | das+rpc | none
    coverage_note: str = ""


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
    partial_history: bool = False
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
    rpc: SolanaRpc, address: str, launch_time: int | None
) -> tuple[WalletProfile, str | None, list[dict[str, Any]]]:
    """Profile a wallet; returns the profile, its first tx signature (if known) and the signature page."""
    sigs = rpc.get_signatures(address, limit=1000)
    profile = WalletProfile(address=address, tx_count=len(sigs))
    first_sig = None
    if sigs:
        oldest = sigs[-1]
        profile.first_seen = oldest.get("blockTime")
        if len(sigs) < 1000:
            first_sig = oldest.get("signature")
    if launch_time and profile.first_seen and len(sigs) < 1000:
        profile.is_fresh = profile.tx_count <= 25 and profile.first_seen >= launch_time - 86_400
    return profile, first_sig, sigs


def collect(
    mint: str,
    rpc: SolanaRpc,
    *,
    max_tx: int = 400,
    early_wallets: int = 6,
    creator_scan_tx: int = 120,
    fetch_metadata: bool = True,
    deep: bool = True,
) -> Snapshot:
    t0 = time.monotonic()
    snap = Snapshot(mint=mint, bonding_curve=derive_bonding_curve(mint), collected_at=time.time())

    # 1. bonding curve --------------------------------------------------------
    try:
        raw = rpc.get_account_data(snap.bonding_curve)
        if raw:
            snap.curve = decode_bonding_curve(raw)
        else:
            snap.notes.append("bonding curve account not found (not a pump.fun token or not yet created)")
    except (RpcError, BorshError) as exc:
        snap.notes.append(f"bonding curve unavailable: {exc}")
    snap.timings["curve"] = time.monotonic() - t0

    # 2. transaction history ----------------------------------------------------
    t1 = time.monotonic()
    try:
        sigs = rpc.get_signatures(mint, limit=1000)
    except RpcError as exc:
        sigs = []
        snap.notes.append(f"signature history unavailable: {exc}")
    snap.total_signatures = len(sigs)
    ok_sigs = [s for s in sigs if s.get("err") is None]
    snap.failed_tx = len(sigs) - len(ok_sigs)
    ok_sigs.reverse()  # oldest first
    if len(ok_sigs) > max_tx:
        head = min(150, max_tx // 2)
        selected = ok_sigs[:head] + ok_sigs[-(max_tx - head) :]
        snap.partial_history = True
        snap.notes.append(f"history truncated: {len(ok_sigs)} successful txs, fetched {len(selected)}")
    else:
        selected = ok_sigs
    if len(sigs) >= 1000:
        snap.partial_history = True
        snap.notes.append("more than 1000 signatures; earliest transactions (create) may be missing")
    signatures = [s["signature"] for s in selected]
    txs = rpc.get_transactions(signatures) if signatures else {}
    order: dict[str, int] = {sig: i for i, sig in enumerate(signatures)}
    trades: list[tuple[int, int, TradeEvent]] = []
    for sig in signatures:
        parsed = parse_transaction(sig, txs.get(sig))
        if parsed is None:
            continue
        for ce in parsed.creates:
            if ce.mint == mint and snap.create is None:
                snap.create = ce
        for tr in parsed.trades:
            if tr.mint == mint:
                trades.append((tr.slot, order[sig], tr))
    trades.sort(key=lambda x: (x[0], x[1]))
    snap.trades = [t[2] for t in trades]
    snap.timings["history"] = time.monotonic() - t1

    # 3. holders ------------------------------------------------------------------
    t2 = time.monotonic()
    curve_ata = derive_curve_token_account(snap.bonding_curve, mint)
    curve_ata_2022 = derive_curve_token_account(snap.bonding_curve, mint, TOKEN_2022_PROGRAM)
    exclude_owners = {snap.bonding_curve}
    holders: list[HolderInfo] | None = None
    try:
        das = rpc.das_get_token_accounts(mint)
    except RpcError as exc:
        das = None
        snap.notes.append(f"DAS token accounts failed: {exc}")
    if das is not None:
        merged: dict[str, int] = {}
        for item in das:
            if item["owner"] in exclude_owners:
                continue
            merged[item["owner"]] = merged.get(item["owner"], 0) + item["amount"]
        holders = [HolderInfo(o, a) for o, a in merged.items() if a > 0]
        snap.holders_source = "das"
    else:
        try:
            largest = rpc.get_token_largest_accounts(mint)
            holders = [
                HolderInfo(item["address"], int(item["amount"]))
                for item in largest
                if item.get("address") not in (curve_ata, curve_ata_2022) and int(item.get("amount", 0)) > 0
            ]
            snap.holders_source = "largest"
            snap.notes.append("holder list limited to the 20 largest token accounts (no DAS endpoint)")
        except RpcError as exc:
            snap.notes.append(f"largest accounts unavailable: {exc}")
    if holders is None:
        balances = derive_balances(snap.trades)
        holders = [HolderInfo(o, a) for o, a in balances.items() if a > 0]
        snap.holders_source = "trades"
    snap.holders = holders
    snap.timings["holders"] = time.monotonic() - t2

    # 4. metadata -------------------------------------------------------------------
    t3 = time.monotonic()
    if fetch_metadata and snap.create and snap.create.uri:
        data = _fetch_json(snap.create.uri)
        if data:
            snap.metadata = data
            snap.metadata_ok = True
        else:
            snap.notes.append("metadata JSON could not be fetched")
    snap.timings["metadata"] = time.monotonic() - t3

    # 5. creator history ------------------------------------------------------------
    t4 = time.monotonic()
    creator = None
    if snap.create:
        creator = snap.create.creator or snap.create.user
    elif snap.curve and snap.curve.creator:
        creator = snap.curve.creator
    launch_time = snap.create.timestamp if snap.create else (snap.trades[0].timestamp if snap.trades else None)
    creator_first_sig = None
    if creator:
        history = CreatorHistory(address=creator)
        candidate_mints: set[str] = set()
        sources: list[str] = []
        try:
            das_mints = rpc.das_get_assets_by_creator(creator)
        except RpcError as exc:
            das_mints = None
            snap.notes.append(f"DAS assets by creator failed: {exc}")
        if das_mints is not None:
            candidate_mints.update(m for m in das_mints if m != mint)
            sources.append("das")
        try:
            snap.creator_profile, creator_first_sig, creator_sigs = _wallet_profile(rpc, creator, launch_time)
            scan_n = creator_scan_tx if das_mints is None else min(creator_scan_tx, 40)
            scan_sigs = [s["signature"] for s in creator_sigs if s.get("err") is None][:scan_n]
            if scan_sigs:
                ctxs = rpc.get_transactions(scan_sigs)
                for sig in scan_sigs:
                    parsed = parse_transaction(sig, ctxs.get(sig))
                    if parsed:
                        candidate_mints.update(m for m in parsed.created_mints if m != mint)
                sources.append("rpc")
                history.coverage_note = f"scanned last {len(scan_sigs)} creator txs"
        except RpcError as exc:
            snap.notes.append(f"creator scan failed: {exc}")
        if candidate_mints:
            mints = sorted(candidate_mints)[:300]
            try:
                datas = rpc.get_multiple_account_data([derive_bonding_curve(m) for m in mints])
            except RpcError as exc:
                datas = []
                snap.notes.append(f"creator curve lookup failed: {exc}")
            for data in datas:
                if not data:
                    continue
                try:
                    st = decode_bonding_curve(data)
                except BorshError:
                    continue
                history.prior_tokens += 1
                if st.complete:
                    history.graduated += 1
                elif st.real_quote_reserves < 2 * 10**9:
                    history.dead += 1
                else:
                    history.active += 1
        history.source = "+".join(sources) if sources else "none"
        snap.creator_history = history
    snap.timings["creator"] = time.monotonic() - t4

    # 6. early buyers -----------------------------------------------------------------
    t5 = time.monotonic()
    if deep and snap.trades:
        devs = snap.dev_addresses
        seen: list[str] = []
        for tr in snap.trades:
            if tr.is_buy and tr.user not in devs and tr.user not in seen:
                seen.append(tr.user)
            if len(seen) >= early_wallets:
                break
        first_sigs: dict[str, str] = {}
        if creator_first_sig and creator:
            first_sigs[creator] = creator_first_sig
        profiles: dict[str, WalletProfile] = {}
        for addr in seen:
            try:
                profile, first_sig, _ = _wallet_profile(rpc, addr, launch_time)
            except RpcError as exc:
                snap.notes.append(f"wallet profile failed for {addr[:6]}: {exc}")
                continue
            profiles[addr] = profile
            if first_sig:
                first_sigs[addr] = first_sig
        if first_sigs:
            addrs = list(first_sigs)
            ftxs = rpc.get_transactions([first_sigs[a] for a in addrs])
            for addr in addrs:
                parsed = parse_transaction(first_sigs[addr], ftxs.get(first_sigs[addr]))
                if parsed and parsed.fee_payer and parsed.fee_payer != addr:
                    if addr in profiles:
                        profiles[addr].funder = parsed.fee_payer
                    elif snap.creator_profile and addr == creator:
                        snap.creator_profile.funder = parsed.fee_payer
        snap.early_wallets = [profiles[a] for a in seen if a in profiles]
    snap.timings["early_wallets"] = time.monotonic() - t5
    snap.timings["total"] = time.monotonic() - t0
    return snap
