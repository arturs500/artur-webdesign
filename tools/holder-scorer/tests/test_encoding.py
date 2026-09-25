import os

import pytest

from holder_scorer.encoding import (
    associated_token_address,
    b58decode,
    b58encode,
    find_program_address,
    is_on_curve,
)
from holder_scorer.pump import PUMP_GLOBAL, PUMP_PROGRAM, derive_bonding_curve

try:  # optional reference implementation
    from solders.pubkey import Pubkey
except ImportError:  # pragma: no cover
    Pubkey = None


def test_base58_vectors():
    assert b58encode(b"") == ""
    assert b58encode(b"\x00") == "1"
    assert b58encode(b"\x00\x00\x01") == "112"
    assert b58decode("112") == b"\x00\x00\x01"
    raw = b58decode("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
    assert len(raw) == 32
    assert b58encode(raw) == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    with pytest.raises(ValueError):
        b58decode("0OIl")


def test_base58_roundtrip_random():
    for _ in range(500):
        raw = os.urandom(int.from_bytes(os.urandom(1), "big") % 40)
        assert b58decode(b58encode(raw)) == raw


def test_known_global_pda():
    addr, bump = find_program_address([b"global"], PUMP_PROGRAM)
    assert b58encode(addr) == PUMP_GLOBAL
    assert bump == 255


def test_bonding_curve_pda_is_deterministic():
    mint = b58encode(os.urandom(32))
    assert derive_bonding_curve(mint) == derive_bonding_curve(mint)
    assert len(b58decode(derive_bonding_curve(mint))) == 32


@pytest.mark.skipif(Pubkey is None, reason="solders not installed")
def test_pda_matches_solders():
    for _ in range(200):
        mint = os.urandom(32)
        mine, mb = find_program_address([b"bonding-curve", mint], PUMP_PROGRAM)
        ref, rb = Pubkey.find_program_address([b"bonding-curve", mint], Pubkey.from_bytes(PUMP_PROGRAM))
        assert bytes(ref) == mine and rb == mb
    for _ in range(1000):
        raw = os.urandom(32)
        assert is_on_curve(raw) == Pubkey.from_bytes(raw).is_on_curve()


@pytest.mark.skipif(Pubkey is None, reason="solders not installed")
def test_ata_matches_solders():
    from solders.pubkey import Pubkey as PK

    token = b58decode("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
    ata_prog = PK.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
    for _ in range(50):
        owner, mint = os.urandom(32), os.urandom(32)
        ref, _ = PK.find_program_address([owner, token, mint], ata_prog)
        assert bytes(ref) == associated_token_address(owner, mint)
