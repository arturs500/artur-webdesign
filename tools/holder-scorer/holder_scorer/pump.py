"""pump.fun program constants and decoders.

Layouts follow the official IDL published in
https://github.com/pump-fun/pump-public-docs (idl/pump.json, September 2026).
Events are emitted through Anchor's self-CPI (``emit_cpi!``), so they show up
as inner instructions of the pump program whose data starts with the Anchor
event tag; older transactions may carry them as ``Program data:`` log lines.
Both paths are decoded. Fields were only ever appended to ``TradeEvent`` and
``BondingCurve``, so decoding stops gracefully when older, shorter payloads
run out of bytes.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Iterable

from .encoding import (
    TOKEN_PROGRAM,
    BorshError,
    BorshReader,
    b58decode,
    b58encode,
    associated_token_address,
    find_program_address,
)

PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_PROGRAM = b58decode(PUMP_PROGRAM_ID)
PUMP_GLOBAL = "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf"
WSOL_MINT = "So11111111111111111111111111111111111111112"
ZERO_PUBKEY = "11111111111111111111111111111111"
TOKEN_DECIMALS = 6
LAMPORTS_PER_SOL = 1_000_000_000

# Global parameters for SOL-quoted curves (docs/PUMP_PROGRAM_README.md).
INITIAL_VIRTUAL_TOKEN_RESERVES = 1_073_000_000_000_000
INITIAL_VIRTUAL_SOL_RESERVES = 30_000_000_000
INITIAL_REAL_TOKEN_RESERVES = 793_100_000_000_000
TOKEN_TOTAL_SUPPLY = 1_000_000_000_000_000

ANCHOR_EVENT_IX_TAG = bytes.fromhex("e445a52e51cb9a1d")
TRADE_EVENT_DISC = bytes.fromhex("bddb7fd34ee661ee")
CREATE_EVENT_DISC = bytes.fromhex("1b72a94ddeeb6376")
COMPLETE_EVENT_DISC = bytes.fromhex("5f72619cd42e9808")
BONDING_CURVE_DISC = bytes.fromhex("17b7f83760d8ac60")

IX_CREATE = bytes.fromhex("181ec828051c0777")
IX_CREATE_V2 = bytes.fromhex("d6904cec5f8b31b4")
IX_BUY = bytes.fromhex("66063d1201daebea")
IX_BUY_EXACT_SOL_IN = bytes.fromhex("38fc74089edfcd5f")
IX_BUY_V2 = bytes.fromhex("b817ee6167c5d33d")
IX_BUY_EXACT_QUOTE_IN_V2 = bytes.fromhex("c2ab1c46684d5b2f")
IX_SELL = bytes.fromhex("33e685a4017f83ad")
IX_SELL_V2 = bytes.fromhex("5df6823ce7e940b2")
CREATE_DISCRIMINATORS = {IX_CREATE, IX_CREATE_V2}


def derive_bonding_curve(mint: str) -> str:
    addr, _ = find_program_address([b"bonding-curve", b58decode(mint)], PUMP_PROGRAM)
    return b58encode(addr)


def derive_curve_token_account(bonding_curve: str, mint: str, token_program: bytes = TOKEN_PROGRAM) -> str:
    return b58encode(associated_token_address(b58decode(bonding_curve), b58decode(mint), token_program))


@dataclass
class BondingCurveState:
    virtual_token_reserves: int
    virtual_quote_reserves: int
    real_token_reserves: int
    real_quote_reserves: int
    token_total_supply: int
    complete: bool
    creator: str | None = None
    is_mayhem_mode: bool | None = None
    is_cashback_coin: bool | None = None
    quote_mint: str | None = None
    creator_fee_bps: int | None = None
    is_holder_reward: bool | None = None

    @property
    def quote_is_sol(self) -> bool:
        # Accounts created before the quote-mint field existed carry zeroed bytes there.
        return self.quote_mint in (None, WSOL_MINT, ZERO_PUBKEY)

    @property
    def progress(self) -> float:
        """Share of the sellable supply already bought (0..1), assuming the standard curve."""
        return self.progress_from(INITIAL_REAL_TOKEN_RESERVES)

    def progress_from(self, initial_real_token_reserves: int) -> float:
        """Progress against the coin's own initial real reserves (from its CreateEvent)."""
        if initial_real_token_reserves <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.real_token_reserves / initial_real_token_reserves))

    @property
    def price_quote_per_token(self) -> float:
        if self.virtual_token_reserves == 0:
            return 0.0
        return (self.virtual_quote_reserves / LAMPORTS_PER_SOL) / (self.virtual_token_reserves / 10**TOKEN_DECIMALS)


def decode_bonding_curve(data: bytes) -> BondingCurveState:
    if len(data) < 8 or data[:8] != BONDING_CURVE_DISC:
        raise BorshError("not a pump.fun BondingCurve account")
    r = BorshReader(data, 8)
    state = BondingCurveState(
        virtual_token_reserves=r.u64(),
        virtual_quote_reserves=r.u64(),
        real_token_reserves=r.u64(),
        real_quote_reserves=r.u64(),
        token_total_supply=r.u64(),
        complete=r.bool(),
    )
    # Fields below were appended over time; older accounts stop early.
    try:
        state.creator = r.pubkey()
        state.is_mayhem_mode = r.bool()
        state.is_cashback_coin = r.bool()
        state.quote_mint = r.pubkey()
        state.creator_fee_bps = r.u64()
        r.bool()  # can_edit_creator_fee, reserved
        state.is_holder_reward = r.bool()
    except BorshError:
        pass
    if state.creator == ZERO_PUBKEY:
        state.creator = None
    return state


@dataclass
class TradeEvent:
    mint: str
    sol_amount: int
    token_amount: int
    is_buy: bool
    user: str
    timestamp: int
    virtual_sol_reserves: int
    virtual_token_reserves: int
    real_sol_reserves: int
    real_token_reserves: int
    creator: str | None = None
    fee: int | None = None
    creator_fee: int | None = None
    ix_name: str | None = None
    mayhem_mode: bool | None = None
    quote_mint: str | None = None
    quote_amount: int | None = None
    virtual_quote_reserves: int | None = None
    real_quote_reserves: int | None = None
    # Filled in by the transaction parser, not part of the event payload.
    signature: str = ""
    slot: int = 0
    block_time: int | None = None

    @property
    def quote_is_sol(self) -> bool:
        return self.quote_mint in (None, WSOL_MINT, ZERO_PUBKEY)

    @property
    def quote_lamports(self) -> int:
        """Amount paid or received in the quote asset's smallest unit."""
        if not self.quote_is_sol and self.quote_amount is not None:
            return self.quote_amount
        if self.sol_amount:
            return self.sol_amount
        return self.quote_amount or 0

    @property
    def price_after(self) -> float | None:
        """Curve price (quote per token, smallest units) after this trade."""
        if self.virtual_token_reserves <= 0:
            return None
        return self.virtual_sol_reserves / self.virtual_token_reserves

    @property
    def price_per_token(self) -> float:
        if self.token_amount == 0:
            return 0.0
        return self.quote_lamports / self.token_amount


def decode_trade_event(payload: bytes) -> TradeEvent:
    r = BorshReader(payload)
    ev = TradeEvent(
        mint=r.pubkey(),
        sol_amount=r.u64(),
        token_amount=r.u64(),
        is_buy=r.bool(),
        user=r.pubkey(),
        timestamp=r.i64(),
        virtual_sol_reserves=r.u64(),
        virtual_token_reserves=r.u64(),
        real_sol_reserves=r.u64(),
        real_token_reserves=r.u64(),
    )
    try:
        r.pubkey()  # fee_recipient
        r.u64()  # fee_basis_points
        ev.fee = r.u64()
        ev.creator = r.pubkey()
        r.u64()  # creator_fee_basis_points
        ev.creator_fee = r.u64()
        r.bool()  # track_volume
        r.u64()  # total_unclaimed_tokens
        r.u64()  # total_claimed_tokens
        r.u64()  # current_sol_volume
        r.i64()  # last_update_timestamp
        ev.ix_name = r.string()
        ev.mayhem_mode = r.bool()
        r.u64()  # cashback_fee_basis_points
        r.u64()  # cashback
        r.u64()  # buyback_fee_basis_points
        r.u64()  # buyback_fee
        n = r.vec_len()  # shareholders: Vec<{address: pubkey, share_bps: u16}>
        for _ in range(n):
            r.pubkey()
            r.u16()
        ev.quote_mint = r.pubkey()
        ev.quote_amount = r.u64()
        ev.virtual_quote_reserves = r.u64()
        ev.real_quote_reserves = r.u64()
    except BorshError:
        pass
    return ev


@dataclass
class CreateEvent:
    name: str
    symbol: str
    uri: str
    mint: str
    bonding_curve: str
    user: str
    creator: str
    timestamp: int
    virtual_token_reserves: int
    virtual_sol_reserves: int
    real_token_reserves: int
    token_total_supply: int
    token_program: str | None = None
    is_mayhem_mode: bool | None = None
    is_cashback_enabled: bool | None = None
    quote_mint: str | None = None
    signature: str = ""
    slot: int = 0
    block_time: int | None = None


def decode_create_event(payload: bytes) -> CreateEvent:
    r = BorshReader(payload)
    ev = CreateEvent(
        name=r.string(),
        symbol=r.string(),
        uri=r.string(),
        mint=r.pubkey(),
        bonding_curve=r.pubkey(),
        user=r.pubkey(),
        creator=r.pubkey(),
        timestamp=r.i64(),
        virtual_token_reserves=r.u64(),
        virtual_sol_reserves=r.u64(),
        real_token_reserves=r.u64(),
        token_total_supply=r.u64(),
    )
    try:
        ev.token_program = r.pubkey()
        ev.is_mayhem_mode = r.bool()
        ev.is_cashback_enabled = r.bool()
        ev.quote_mint = r.pubkey()
    except BorshError:
        pass
    return ev


@dataclass
class ParsedTx:
    signature: str
    slot: int
    block_time: int | None
    failed: bool
    fee_payer: str
    account_keys: list[str]
    trades: list[TradeEvent] = field(default_factory=list)
    creates: list[CreateEvent] = field(default_factory=list)
    completed_mints: list[str] = field(default_factory=list)
    created_mints: list[str] = field(default_factory=list)
    mayhem_token_vault: str | None = None  # create_v2 coins park part of the supply here


def _all_account_keys(tx: dict[str, Any]) -> list[str]:
    msg = tx["transaction"]["message"]
    keys = list(msg.get("accountKeys", []))
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in keys]
    loaded = (tx.get("meta") or {}).get("loadedAddresses") or {}
    keys += list(loaded.get("writable", []))
    keys += list(loaded.get("readonly", []))
    return keys


def _iter_instructions(tx: dict[str, Any]) -> Iterable[dict[str, Any]]:
    msg = tx["transaction"]["message"]
    for ix in msg.get("instructions", []):
        yield ix
    for group in (tx.get("meta") or {}).get("innerInstructions") or []:
        for ix in group.get("instructions", []):
            yield ix


def _event_payloads(tx: dict[str, Any], keys: list[str]) -> tuple[list[bytes], list[tuple[bytes, dict[str, Any]]]]:
    """Return raw event bytes (discriminator + body) from CPI and log paths, plus decoded pump instructions."""
    payloads: list[bytes] = []
    pump_ixs: list[tuple[bytes, dict[str, Any]]] = []
    seen: set[bytes] = set()
    for ix in _iter_instructions(tx):
        idx = ix.get("programIdIndex")
        if idx is None or idx >= len(keys) or keys[idx] != PUMP_PROGRAM_ID:
            continue
        data = ix.get("data")
        if not isinstance(data, str):
            continue
        try:
            raw = b58decode(data)
        except ValueError:
            continue
        if raw[:8] == ANCHOR_EVENT_IX_TAG and len(raw) > 16:
            body = raw[8:]
            if body not in seen:
                seen.add(body)
                payloads.append(body)
        else:
            pump_ixs.append((raw, ix))
    for line in (tx.get("meta") or {}).get("logMessages") or []:
        if not line.startswith("Program data: "):
            continue
        try:
            raw = base64.b64decode(line[len("Program data: "):])
        except Exception:
            continue
        if len(raw) > 8 and raw[:8] in (TRADE_EVENT_DISC, CREATE_EVENT_DISC, COMPLETE_EVENT_DISC) and raw not in seen:
            seen.add(raw)
            payloads.append(raw)
    return payloads, pump_ixs


def parse_transaction(signature: str, tx: dict[str, Any] | None) -> ParsedTx | None:
    """Extract pump.fun events from a ``getTransaction`` result (json encoding)."""
    if not tx or "transaction" not in tx:
        return None
    meta = tx.get("meta") or {}
    keys = _all_account_keys(tx)
    parsed = ParsedTx(
        signature=signature,
        slot=int(tx.get("slot", 0)),
        block_time=tx.get("blockTime"),
        failed=meta.get("err") is not None,
        fee_payer=keys[0] if keys else "",
        account_keys=keys,
    )
    if parsed.failed:
        return parsed
    payloads, pump_ixs = _event_payloads(tx, keys)
    for payload in payloads:
        disc, body = payload[:8], payload[8:]
        try:
            if disc == TRADE_EVENT_DISC:
                ev = decode_trade_event(body)
                ev.signature, ev.slot, ev.block_time = signature, parsed.slot, parsed.block_time
                parsed.trades.append(ev)
            elif disc == CREATE_EVENT_DISC:
                ce = decode_create_event(body)
                ce.signature, ce.slot, ce.block_time = signature, parsed.slot, parsed.block_time
                parsed.creates.append(ce)
                parsed.created_mints.append(ce.mint)
            elif disc == COMPLETE_EVENT_DISC:
                r = BorshReader(body)
                r.pubkey()  # user
                parsed.completed_mints.append(r.pubkey())
        except BorshError:
            continue
    # Create instructions: fallback mint detection and the mayhem vault of create_v2 coins.
    for raw, ix in pump_ixs:
        if raw[:8] not in CREATE_DISCRIMINATORS:
            continue
        accs = ix.get("accounts") or []
        if not parsed.created_mints and accs and accs[0] < len(keys):
            parsed.created_mints.append(keys[accs[0]])
        if raw[:8] == IX_CREATE_V2 and len(accs) > 13 and accs[13] < len(keys):
            parsed.mayhem_token_vault = keys[accs[13]]
    return parsed
