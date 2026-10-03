"""Low-level Solana encoding helpers without external dependencies.

Covers base58, Borsh reading, program-derived addresses (PDA) and the
associated-token-account derivation. Everything here is pure Python so the
scorer runs anywhere Python 3.10+ runs.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ALPHABET_INDEX = {c: i for i, c in enumerate(_ALPHABET)}


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_ALPHABET[rem])
    pad = 0
    for b in raw:
        if b == 0:
            pad += 1
        else:
            break
    return (b"1" * pad + bytes(reversed(out))).decode("ascii")


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text.encode("ascii"):
        try:
            n = n * 58 + _ALPHABET_INDEX[ch]
        except KeyError as exc:
            raise ValueError(f"invalid base58 character {ch!r}") from exc
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = 0
    for ch in text:
        if ch == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + body


# --- ed25519 on-curve test (mirrors curve25519-dalek decompress) ------------
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def is_on_curve(point: bytes) -> bool:
    """True when the 32 bytes decompress to a valid ed25519 point.

    Mirrors ``CompressedEdwardsY::decompress`` from curve25519-dalek, which
    Solana uses for ``Pubkey::is_on_curve``: the sign bit is ignored, the
    y coordinate is reduced modulo p, and the point is valid when
    x^2 = (y^2 - 1) / (d*y^2 + 1) has a square root.
    """
    if len(point) != 32:
        raise ValueError("point must be 32 bytes")
    y = int.from_bytes(point, "little") & ((1 << 255) - 1)
    y %= _P
    y2 = y * y % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    if u == 0:
        return True
    x2 = u * pow(v, _P - 2, _P) % _P
    return pow(x2, (_P - 1) // 2, _P) == 1


def find_program_address(seeds: list[bytes], program_id: bytes) -> tuple[bytes, int]:
    if len(program_id) != 32:
        raise ValueError("program id must be 32 bytes")
    for seed in seeds:
        if len(seed) > 32:
            raise ValueError("seed longer than 32 bytes")
    for bump in range(255, -1, -1):
        h = hashlib.sha256()
        for seed in seeds:
            h.update(seed)
        h.update(bytes([bump]))
        h.update(program_id)
        h.update(b"ProgramDerivedAddress")
        candidate = h.digest()
        if not is_on_curve(candidate):
            return candidate, bump
    raise ValueError("unable to find a viable program address bump seed")


TOKEN_PROGRAM = b58decode("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM = b58decode("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ASSOCIATED_TOKEN_PROGRAM = b58decode("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")


def associated_token_address(owner: bytes, mint: bytes, token_program: bytes = TOKEN_PROGRAM) -> bytes:
    addr, _ = find_program_address([owner, token_program, mint], ASSOCIATED_TOKEN_PROGRAM)
    return addr


# --- Borsh reader -----------------------------------------------------------
class BorshError(ValueError):
    pass


@dataclass
class BorshReader:
    data: bytes
    pos: int = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def _take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise BorshError(f"need {n} bytes at offset {self.pos}, have {self.remaining()}")
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def u8(self) -> int:
        return self._take(1)[0]

    def bool(self) -> bool:
        b = self.u8()
        if b not in (0, 1):
            raise BorshError(f"invalid bool byte {b}")
        return b == 1

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self._take(8))[0]

    def pubkey(self) -> str:
        return b58encode(self._take(32))

    def string(self) -> str:
        n = self.u32()
        if n > 10_000:
            raise BorshError(f"unreasonable string length {n}")
        return self._take(n).decode("utf-8", errors="replace")

    def vec_len(self) -> int:
        n = self.u32()
        if n > 100_000:
            raise BorshError(f"unreasonable vec length {n}")
        return n
