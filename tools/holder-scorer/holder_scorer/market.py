"""Market numbers from DexScreener (free, no key) and the SOL price.

DexScreener indexes pump.fun tokens on the bonding curve ("pumpfun") and
after graduation ("pumpswap", "raydium"), so it is the one source that gives
market cap, liquidity, volume and buy/sell counts for any token, including
the ones the on-chain collector cannot decode any more. Everything here is
best effort: a failed request simply returns ``None``.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
WSOL = "So11111111111111111111111111111111111111112"


@dataclass
class MarketData:
    source: str
    dex_id: str | None = None
    pair_address: str | None = None
    name: str | None = None
    symbol: str | None = None
    price_usd: float | None = None
    price_native: float | None = None
    market_cap_usd: float | None = None
    fdv_usd: float | None = None
    liquidity_usd: float | None = None
    liquidity_quote: float | None = None  # SOL side of the pool
    volume_m5_usd: float | None = None
    volume_h1_usd: float | None = None
    volume_h24_usd: float | None = None
    buys_m5: int | None = None
    sells_m5: int | None = None
    buys_h1: int | None = None
    sells_h1: int | None = None
    price_change_m5: float | None = None
    price_change_h1: float | None = None
    pair_created_at: float | None = None  # unix seconds
    socials: int = 0
    fetched_at: float = field(default_factory=time.time)

    @property
    def sol_usd(self) -> float | None:
        if self.price_usd and self.price_native and self.price_native > 0:
            return self.price_usd / self.price_native
        return None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def _num(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _int(x: Any) -> int | None:
    v = _num(x)
    return int(v) if v is not None else None


def parse_pairs(payload: dict[str, Any] | None, mint: str) -> MarketData | None:
    """Pick the most liquid SOL pair of the token from a DexScreener response."""
    pairs = (payload or {}).get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        return None
    candidates = [p for p in pairs if isinstance(p, dict) and (p.get("baseToken") or {}).get("address") == mint and p.get("chainId", "solana") == "solana"]
    if not candidates:
        candidates = [p for p in pairs if isinstance(p, dict)]
    if not candidates:
        return None

    def liq(p: dict[str, Any]) -> float:
        return _num((p.get("liquidity") or {}).get("usd")) or 0.0

    sol_pairs = [p for p in candidates if (p.get("quoteToken") or {}).get("address") == WSOL]
    pool = sol_pairs or candidates
    best = max(pool, key=liq)
    txns = best.get("txns") or {}
    vol = best.get("volume") or {}
    chg = best.get("priceChange") or {}
    info = best.get("info") or {}
    socials = len(info.get("socials") or []) + len(info.get("websites") or [])
    created = _num(best.get("pairCreatedAt"))
    return MarketData(
        source="dexscreener",
        dex_id=best.get("dexId"),
        pair_address=best.get("pairAddress"),
        name=(best.get("baseToken") or {}).get("name"),
        symbol=(best.get("baseToken") or {}).get("symbol"),
        price_usd=_num(best.get("priceUsd")),
        price_native=_num(best.get("priceNative")),
        market_cap_usd=_num(best.get("marketCap")),
        fdv_usd=_num(best.get("fdv")),
        liquidity_usd=_num((best.get("liquidity") or {}).get("usd")),
        liquidity_quote=_num((best.get("liquidity") or {}).get("quote")),
        volume_m5_usd=_num(vol.get("m5")),
        volume_h1_usd=_num(vol.get("h1")),
        volume_h24_usd=_num(vol.get("h24")),
        buys_m5=_int((txns.get("m5") or {}).get("buys")),
        sells_m5=_int((txns.get("m5") or {}).get("sells")),
        buys_h1=_int((txns.get("h1") or {}).get("buys")),
        sells_h1=_int((txns.get("h1") or {}).get("sells")),
        price_change_m5=_num(chg.get("m5")),
        price_change_h1=_num(chg.get("h1")),
        pair_created_at=(created / 1000.0) if created and created > 10**11 else created,
        socials=socials,
    )


def fetch_market(mint: str, timeout: float = 4.0, session: requests.Session | None = None) -> MarketData | None:
    try:
        resp = (session or requests).get(DEXSCREENER_URL.format(mint=mint), timeout=timeout, headers={"accept": "application/json"})
        if resp.status_code != 200:
            return None
        return parse_pairs(resp.json(), mint)
    except (requests.RequestException, ValueError):
        return None


_price_lock = threading.Lock()
_price_cache: dict[str, Any] = {"value": None, "at": 0.0}


def sol_usd(hint: float | None = None, max_age_s: float = 120.0) -> float | None:
    """SOL price in USD: the hint (from a DexScreener pair), else CoinGecko (cached), else env SOL_USD."""
    if hint and hint > 0:
        with _price_lock:
            _price_cache.update(value=hint, at=time.time())
        return hint
    with _price_lock:
        if _price_cache["value"] and time.time() - _price_cache["at"] < max_age_s:
            return _price_cache["value"]
    value: float | None = None
    try:
        resp = requests.get(COINGECKO_URL, timeout=4.0)
        if resp.status_code == 200:
            value = _num(((resp.json() or {}).get("solana") or {}).get("usd"))
    except (requests.RequestException, ValueError):
        value = None
    if value is None:
        value = _num(os.environ.get("SOL_USD"))
    if value:
        with _price_lock:
            _price_cache.update(value=value, at=time.time())
    return value
