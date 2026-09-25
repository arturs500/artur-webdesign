"""holder_scorer: judge whether a pump.fun token is likely to gain holders.

Minimal use from a Python bot::

    from holder_scorer import evaluate_token

    verdict = evaluate_token(mint, rpc_url="https://mainnet.helius-rpc.com/?api-key=...")
    if verdict.buy_signal:      # label == "JA"
        ...place the buy...
    print(verdict.score, verdict.label, verdict.hard_fails)
"""
from __future__ import annotations

import os
import time

from .collect import Snapshot, collect
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

__version__ = "0.1.0"


def make_rpc(rpc_url: str | None = None, rps: float | None = None) -> SolanaRpc:
    url = rpc_url or os.environ.get("SOLANA_RPC_URL")
    if not url:
        raise ValueError("RPC-URL fehlt: --rpc angeben oder SOLANA_RPC_URL setzen")
    rate = rps if rps is not None else float(os.environ.get("SOLANA_RPC_RPS", "10"))
    return SolanaRpc(url, rps=rate)


def evaluate_token(
    mint: str,
    rpc_url: str | None = None,
    rpc: SolanaRpc | None = None,
    config: ScoringConfig | None = None,
    deep: bool = True,
    now: float | None = None,
    max_tx: int = 400,
) -> Verdict:
    """Collect, featurize and score one token. Raises RpcError on transport failure."""
    client = rpc or make_rpc(rpc_url)
    snap = collect(mint, client, deep=deep, max_tx=max_tx)
    feats = compute_features(snap, now if now is not None else time.time())
    verdict = score_features(feats, config)
    verdict.notes.extend(n for n in snap.notes if n not in verdict.notes)
    return verdict
