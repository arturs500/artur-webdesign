"""holder_scorer: judge whether a pump.fun token is likely to gain holders.

Minimal use from a Python bot::

    from holder_scorer import evaluate_token, make_rpc

    rpc = make_rpc("https://mainnet.helius-rpc.com/?api-key=...")   # create once, reuse
    verdict = evaluate_token(mint, rpc=rpc)
    if verdict.buy_signal:      # label == "JA"
        ...place the buy...
    print(verdict.score, verdict.label, verdict.hard_fails)
"""
from __future__ import annotations

import os
import threading
import time

from .collect import ProfileCache, Snapshot, collect
from .features import Features, compute_features
from .rpc import RpcError, SolanaRpc
from .scoring import (
    LABEL_GRADUATED,
    LABEL_NO,
    LABEL_NO_DATA,
    LABEL_TOO_EARLY,
    LABEL_UNCLEAR,
    LABEL_YES,
    FactorResult,
    ScoringConfig,
    Verdict,
    format_verdict,
    score_features,
)

__all__ = [
    "evaluate_token",
    "collect",
    "compute_features",
    "score_features",
    "format_verdict",
    "make_rpc",
    "ProfileCache",
    "Snapshot",
    "Features",
    "Verdict",
    "FactorResult",
    "ScoringConfig",
    "SolanaRpc",
    "RpcError",
    "LABEL_YES",
    "LABEL_UNCLEAR",
    "LABEL_NO",
    "LABEL_TOO_EARLY",
    "LABEL_GRADUATED",
    "LABEL_NO_DATA",
]

__version__ = "0.2.0"

_clients: dict[tuple[str, float], SolanaRpc] = {}
_clients_lock = threading.Lock()
_default_cache = ProfileCache()


def make_rpc(rpc_url: str | None = None, rps: float | None = None) -> SolanaRpc:
    """Return one shared client per URL so the rate limiter and connection pool persist across calls."""
    url = rpc_url or os.environ.get("SOLANA_RPC_URL")
    if not url:
        raise ValueError("RPC-URL fehlt: --rpc angeben oder SOLANA_RPC_URL setzen")
    rate = rps if rps is not None else float(os.environ.get("SOLANA_RPC_RPS", "10"))
    with _clients_lock:
        client = _clients.get((url, rate))
        if client is None:
            client = SolanaRpc(url, rps=rate)
            _clients[(url, rate)] = client
        return client


def evaluate_token(
    mint: str,
    rpc_url: str | None = None,
    rpc: SolanaRpc | None = None,
    config: ScoringConfig | None = None,
    deep: bool = True,
    now: float | None = None,
    max_tx: int = 400,
    cache: ProfileCache | None = None,
    launch_hint: float | None = None,
    signatures: list[dict] | None = None,
) -> Verdict:
    """Collect, featurize and score one token.

    Raises ``RpcError`` when the endpoint cannot serve the mandatory calls
    (curve account, signature list); optional data degrades to "unknown".
    ``launch_hint`` is the time the launch was observed (used for the token's
    age when its create transaction is not in the fetched history), and
    ``signatures`` may pass an already fetched signature page for the mint.
    """
    client = rpc or make_rpc(rpc_url)
    when = now if now is not None else time.time()
    snap = collect(
        mint, client, deep=deep, max_tx=max_tx, cache=cache or _default_cache, launch_hint=launch_hint, now=when, signatures=signatures
    )
    feats = compute_features(snap, when)
    verdict = score_features(feats, config)
    verdict.notes.extend(n for n in snap.notes if n not in verdict.notes)
    return verdict
