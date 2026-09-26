"""Borsh writer and fake-transaction builders for the tests."""
from __future__ import annotations

import base64
import os
import struct

from holder_scorer.encoding import b58encode
from holder_scorer.pump import (
    ANCHOR_EVENT_IX_TAG,
    BONDING_CURVE_DISC,
    CREATE_EVENT_DISC,
    PUMP_PROGRAM_ID,
    TRADE_EVENT_DISC,
)


class W:
    def __init__(self) -> None:
        self.b = bytearray()

    def u8(self, v: int) -> "W":
        self.b += struct.pack("<B", v)
        return self

    def u16(self, v: int) -> "W":
        self.b += struct.pack("<H", v)
        return self

    def u32(self, v: int) -> "W":
        self.b += struct.pack("<I", v)
        return self

    def u64(self, v: int) -> "W":
        self.b += struct.pack("<Q", v)
        return self

    def i64(self, v: int) -> "W":
        self.b += struct.pack("<q", v)
        return self

    def boolean(self, v: bool) -> "W":
        return self.u8(1 if v else 0)

    def pubkey(self, raw: bytes) -> "W":
        assert len(raw) == 32
        self.b += raw
        return self

    def string(self, s: str) -> "W":
        enc = s.encode()
        return self.u32(len(enc)).raw(enc)

    def raw(self, data: bytes) -> "W":
        self.b += data
        return self

    def bytes(self) -> bytes:
        return bytes(self.b)


def key() -> bytes:
    return os.urandom(32)


def trade_event_bytes(
    mint: bytes,
    user: bytes,
    sol: int,
    tokens: int,
    is_buy: bool,
    ts: int,
    creator: bytes | None = None,
    full: bool = True,
    ix_name: str = "buy",
    reserves: tuple[int, int] | None = None,
) -> bytes:
    """Borsh-encode a TradeEvent. ``reserves`` = (virtual SOL lamports, virtual token raw units) after the trade."""
    if reserves is None:
        v_sol, v_tokens = 30_000_000_000 + sol, 1_073_000_000_000_000 - tokens
    else:
        v_sol, v_tokens = reserves
    w = (
        W()
        .pubkey(mint)
        .u64(sol)
        .u64(tokens)
        .boolean(is_buy)
        .pubkey(user)
        .i64(ts)
        .u64(v_sol)
        .u64(v_tokens)
        .u64(max(0, v_sol - 30_000_000_000))
        .u64(max(0, v_tokens - 279_900_000_000_000))
    )
    if full:
        w.pubkey(key()).u64(100).u64(sol // 100).pubkey(creator or key()).u64(30).u64(sol // 300)
        w.boolean(True).u64(0).u64(0).u64(sol).i64(ts)
        w.string(ix_name).boolean(False).u64(0).u64(0).u64(0).u64(0)
        w.u32(1).pubkey(key()).u16(10_000)  # one shareholder
        w.pubkey(bytes([0] * 32)).u64(sol).u64(30_000_000_000 + sol).u64(sol).u64(0).u64(0)
    return w.bytes()


def create_event_bytes(name: str, symbol: str, uri: str, mint: bytes, curve: bytes, user: bytes, creator: bytes, ts: int) -> bytes:
    return (
        W()
        .string(name)
        .string(symbol)
        .string(uri)
        .pubkey(mint)
        .pubkey(curve)
        .pubkey(user)
        .pubkey(creator)
        .i64(ts)
        .u64(1_073_000_000_000_000)
        .u64(30_000_000_000)
        .u64(793_100_000_000_000)
        .u64(1_000_000_000_000_000)
        .pubkey(key())
        .boolean(False)
        .boolean(False)
        .pubkey(bytes([0] * 32))
        .u64(30_000_000_000)
        .u64(30)
        .boolean(False)
        .bytes()
    )


def bonding_curve_bytes(
    vt: int, vq: int, rt: int, rq: int, supply: int, complete: bool, creator: bytes | None = None, new_layout: bool = True
) -> bytes:
    w = W().raw(BONDING_CURVE_DISC).u64(vt).u64(vq).u64(rt).u64(rq).u64(supply).boolean(complete)
    if new_layout:
        w.pubkey(creator or key()).boolean(False).boolean(False).pubkey(bytes([0] * 32)).u64(0).boolean(False).boolean(False)
    return w.bytes()


def fake_tx(
    signature: str,
    slot: int,
    block_time: int,
    fee_payer: bytes,
    events: list[bytes],
    via: str = "cpi",
    failed: bool = False,
    extra_instructions: list[dict] | None = None,
) -> dict:
    """Build a getTransaction(json) result carrying the given raw events."""
    keys = [b58encode(fee_payer), PUMP_PROGRAM_ID, b58encode(key())]
    inner = []
    logs = ["Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]"]
    for ev in events:
        if via == "cpi":
            inner.append({"programIdIndex": 1, "accounts": [2], "data": b58encode(ANCHOR_EVENT_IX_TAG + ev), "stackHeight": 2})
        else:
            logs.append("Program data: " + base64.b64encode(ev).decode())
    return {
        "slot": slot,
        "blockTime": block_time,
        "transaction": {
            "message": {
                "accountKeys": keys,
                "instructions": (extra_instructions or []) + [{"programIdIndex": 1, "accounts": [2], "data": "1111"}],
            },
            "signatures": [signature],
        },
        "meta": {
            "err": {"InstructionError": [0, "Custom"]} if failed else None,
            "logMessages": logs,
            "innerInstructions": [{"index": 0, "instructions": inner}] if inner else [],
            "loadedAddresses": {"writable": [], "readonly": []},
        },
    }


__all__ = [
    "W",
    "key",
    "trade_event_bytes",
    "create_event_bytes",
    "bonding_curve_bytes",
    "fake_tx",
    "TRADE_EVENT_DISC",
    "CREATE_EVENT_DISC",
]
