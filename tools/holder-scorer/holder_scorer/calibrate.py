"""Record verdicts, collect outcomes later, and measure which factors work.

Workflow:

1. ``score --record datei.jsonl`` (or ``watch --record``) appends each verdict
   together with all features.
2. ``outcome --file datei.jsonl`` re-checks every recorded token whose horizon
   has passed and appends one outcome line per token (the file is
   append-only, so a concurrently running ``watch --record`` never loses data
   and Ctrl-C keeps the work done so far).
3. ``evaluate --file datei.jsonl`` prints hit rates per label, per-factor
   tercile analysis and a small logistic regression, so weights can be tuned
   on real observations instead of guesses.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any

from .collect import ProfileCache, collect
from .encoding import BorshError
from .features import DUST_TOKENS, compute_features
from .pump import decode_bonding_curve, derive_bonding_curve
from .rpc import RpcError, SolanaRpc
from .scoring import LABEL_NO, LABEL_UNCLEAR, LABEL_YES, Verdict

NUMERIC_FACTORS = [
    "holder_growth_60s",
    "new_buyers_60s",
    "outside_buyers_120s",
    "outside_buys_120s",
    "unique_outside_buyers",
    "buy_sell_ratio_120s",
    "organic_net_flow_120s_sol",
    "price_change_60s",
    "creation_window_share",
    "creation_window_held_share",
    "creation_window_sold_share",
    "early_sold_share",
    "early_overhang",
    "top10_share",
    "largest_float_share",
    "top3_float_share",
    "dev_buy_share",
    "dev_sold_share",
    "early_fresh_wallets",
    "early_funded_by_creator",
    "creator_prior_tokens",
    "creator_graduated",
    "creator_dead",
    "creator_seconds_since_prev_launch",
    "creator_launch_rate_per_h",
    "socials_count",
    "small_buy_share",
    "bot_buy_share",
    "wash_share",
    "failed_after_30s_share",
    "progress",
    "holders_now",
]


LABEL_PREFILTER = "VORFILTER"
MAX_OUTCOME_ATTEMPTS = 3


def append_record(path: str, verdict: Verdict) -> None:
    rec = {
        "recorded_at": time.time(),
        "mint": verdict.mint,
        "label": verdict.label,
        "score": round(verdict.score, 1),
        "hard_fails": verdict.hard_fails,
        "factors": {x.name: round(x.points, 2) for x in verdict.factors},
        "features": verdict.features.to_dict(),
        "outcome": None,
    }
    _append_line(path, rec)


def append_prefilter_record(path: str, mint: str, signatures: int) -> None:
    """Record a launch the watch prefilter skipped, so ``outcome`` can show whether it grew anyway."""
    _append_line(path, {"recorded_at": time.time(), "mint": mint, "label": LABEL_PREFILTER, "signatures": signatures, "features": None, "outcome": None})


def _append_line(path: str, obj: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_records(path: str) -> list[dict[str, Any]]:
    """Read the append-only file and join outcome lines onto their base records."""
    if not os.path.exists(path):
        return []
    base: list[dict[str, Any]] = []
    index: dict[tuple[str, float], dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            if "outcome_for" in obj:
                outcomes.append(obj)
            elif "mint" in obj and "recorded_at" in obj:
                base.append(obj)
                index[(obj["mint"], obj["recorded_at"])] = obj
    for o in outcomes:
        ref = o.get("outcome_for") or {}
        rec = index.get((ref.get("mint"), ref.get("recorded_at")))
        if rec is not None:
            rec["outcome"] = o.get("outcome")
    return base


def _probe_holders(rpc: SolanaRpc, mint: str, now: float) -> tuple[int | None, float | None, bool | None]:
    """Cheap outcome probe: bonding-curve state plus a DAS holder count; full collect only without DAS."""
    progress = complete = None
    raw = rpc.get_account_data(derive_bonding_curve(mint))
    if raw:
        try:
            st = decode_bonding_curve(raw)
            progress, complete = st.progress, st.complete
        except BorshError:
            pass
    das = rpc.das_get_token_accounts(mint)
    if das is not None:
        merged: dict[str, int] = {}
        curve = derive_bonding_curve(mint)
        for item in das:
            if item["owner"] == curve:
                continue
            merged[item["owner"]] = merged.get(item["owner"], 0) + item["amount"]
        return sum(1 for a in merged.values() if a > DUST_TOKENS), progress, complete
    snap = collect(mint, rpc, deep=False, fetch_metadata=False, max_tx=400, use_das=False, creator_scan_tx=0, now=now)
    feats = compute_features(snap, now)
    return feats.holders_now, progress if progress is not None else feats.progress, complete if complete is not None else feats.complete


def _outcome_final(outcome: Any, base_known: bool) -> bool:
    """An outcome is final when it carries a result, or the base count can never be known, or attempts are used up."""
    if not isinstance(outcome, dict):
        return outcome is not None
    if outcome.get("grew") is not None:
        return True
    if not base_known and "holders_later" in outcome:
        return True  # nothing to compare against; the later count is kept for the VORFILTER statistics
    return int(outcome.get("attempts") or 1) >= MAX_OUTCOME_ATTEMPTS


def update_outcomes(path: str, rpc: SolanaRpc, horizon_s: float = 900.0, growth_target: float = 1.5) -> int:
    """Append outcomes for records older than ``horizon_s``. Returns the count checked.

    Transient failures and unknown holder counts are retried on later runs (up to
    ``MAX_OUTCOME_ATTEMPTS`` times); a later outcome line supersedes an earlier one.
    """
    records = load_records(path)
    checked = 0
    for rec in records:
        now = time.time()
        mint, recorded_at = rec.get("mint"), rec.get("recorded_at")
        if not mint or recorded_at is None or recorded_at + horizon_s > now:
            continue
        base = (rec.get("features") or {}).get("holders_now")
        prev = rec.get("outcome")
        if _outcome_final(prev, base is not None):
            continue
        attempts = (int(prev.get("attempts") or 1) if isinstance(prev, dict) else 0) + 1
        try:
            later, progress, complete = _probe_holders(rpc, mint, now)
        except Exception as exc:  # noqa: BLE001 - one bad record must not abort the run
            if "abgebrochen" in str(exc):
                raise
            _append_line(path, {"outcome_for": {"mint": mint, "recorded_at": recorded_at}, "outcome": {"error": str(exc), "checked_at": now, "attempts": attempts}})
            checked += 1
            continue
        grew = None
        if base is not None and later is not None:
            grew = later >= max(base * growth_target, base + 5)
        outcome = {
            "checked_at": now,
            "elapsed_s": round(now - recorded_at),
            "holders_at_record": base,
            "holders_later": later,
            "progress_later": progress,
            "complete_later": complete,
            "grew": grew,
            "attempts": attempts,
        }
        if grew is None and base is not None:
            outcome["error"] = "holder count unknown at check"
        _append_line(path, {"outcome_for": {"mint": mint, "recorded_at": recorded_at}, "outcome": outcome})
        checked += 1
    return checked


@dataclass
class EvalReport:
    n_total: int
    n_with_outcome: int
    base_rate: float | None
    per_label: dict[str, tuple[int, float | None]]
    terciles: dict[str, list[tuple[str, int, float | None]]]
    coefficients: dict[str, float]
    text: str


def _num(rec: dict[str, Any], name: str) -> float | None:
    feats = rec.get("features")
    if not isinstance(feats, dict):
        return None
    v = feats.get(name)
    if isinstance(v, bool):
        v = int(v)
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _logistic_fit(rows: list[list[float]], labels: list[int], names: list[str], epochs: int = 400, lr: float = 0.05, l2: float = 0.01) -> dict[str, float]:
    if not rows or len(set(labels)) < 2:
        return {}
    k = len(names)
    means = [sum(r[j] for r in rows) / len(rows) for j in range(k)]
    stds = [max(1e-9, math.sqrt(sum((r[j] - means[j]) ** 2 for r in rows) / len(rows))) for j in range(k)]
    x = [[(r[j] - means[j]) / stds[j] for j in range(k)] for r in rows]
    w = [0.0] * k
    b = 0.0
    n = len(x)
    for _ in range(epochs):
        gw = [0.0] * k
        gb = 0.0
        for xi, yi in zip(x, labels):
            z = b + sum(wj * xj for wj, xj in zip(w, xi))
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            err = p - yi
            gb += err
            for j in range(k):
                gw[j] += err * xi[j]
        b -= lr * gb / n
        for j in range(k):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
    return dict(zip(names, w))


def evaluate(path: str) -> EvalReport:
    all_records = load_records(path)
    records = [r for r in all_records if isinstance(r.get("outcome"), dict) and r["outcome"].get("grew") is not None]
    lines: list[str] = [f"{len(all_records)} Aufzeichnungen, {len(records)} mit Ergebnis"]
    if not records:
        lines.append("Noch keine Ergebnisse. Erst `outcome` laufen lassen, sobald der Zeithorizont verstrichen ist.")
        return EvalReport(len(all_records), 0, None, {}, {}, {}, "\n".join(lines))
    labels = [1 if r["outcome"]["grew"] else 0 for r in records]
    base_rate = sum(labels) / len(labels)
    lines.append(f"Basisrate (Holder gewachsen): {base_rate * 100:.1f} %")
    bad = sum(1 for r in records if not isinstance(r.get("features"), dict))
    if bad:
        lines.append(f"{bad} Aufzeichnungen ohne verwertbare Merkmale (nur in der Basisrate enthalten)")
    per_label: dict[str, tuple[int, float | None]] = {}
    for lab in (LABEL_YES, LABEL_UNCLEAR, LABEL_NO):
        subset = [l for r, l in zip(records, labels) if r.get("label") == lab]
        per_label[lab] = (len(subset), (sum(subset) / len(subset)) if subset else None)
        rate = f"{per_label[lab][1] * 100:.1f} %" if subset else "–"
        lines.append(f"  Urteil {lab:<7} n={len(subset):<4} Trefferquote {rate}")
    for flag in ("is_mayhem", "quote_is_sol"):
        subset = [l for r, l in zip(records, labels) if (r.get("features") or {}).get(flag) is True]
        if subset:
            lines.append(f"  {flag}=True  n={len(subset):<4} Trefferquote {sum(subset) / len(subset) * 100:.1f} %")
    pre = [r for r in all_records if r.get("label") == LABEL_PREFILTER and isinstance(r.get("outcome"), dict) and r["outcome"].get("holders_later") is not None]
    if pre:
        grown = sum(1 for r in pre if (r["outcome"].get("holders_later") or 0) >= 20)
        lines.append(f"  Vorfilter-Abweisungen mit Ergebnis: n={len(pre)}, davon später mindestens 20 Holder: {grown / len(pre) * 100:.1f} %")
    terciles: dict[str, list[tuple[str, int, float | None]]] = {}
    lines.append("\nFaktoren nach Dritteln (Anteil gewachsen je Drittel, niedrig → hoch):")
    for name in NUMERIC_FACTORS:
        pairs = [(v, l) for r, l in zip(records, labels) if (v := _num(r, name)) is not None]
        if len(pairs) < 9:
            continue
        pairs.sort(key=lambda p: p[0])
        third = len(pairs) // 3
        parts = [pairs[:third], pairs[third : 2 * third], pairs[2 * third :]]
        row = []
        for tag, part in zip(("niedrig", "mittel", "hoch"), parts):
            rate = sum(l for _, l in part) / len(part) if part else None
            row.append((tag, len(part), rate))
        terciles[name] = row
        lines.append(
            f"  {name:<32} " + "  ".join(f"{tag} {rate * 100:5.1f} %" if rate is not None else f"{tag}   –" for tag, _, rate in row)
        )
    usable = [n for n in NUMERIC_FACTORS if all(_num(r, n) is not None for r in records)]
    coefficients = (
        _logistic_fit([[_num(r, n) for n in usable] for r in records], labels, usable)  # type: ignore[misc]
        if len(records) >= 30 and usable
        else {}
    )
    if coefficients:
        lines.append("\nLogistische Regression (standardisierte Koeffizienten, positiv = spricht für Wachstum):")
        for name, coef in sorted(coefficients.items(), key=lambda kv: -abs(kv[1])):
            lines.append(f"  {name:<32} {coef:+.3f}")
    else:
        lines.append("\nRegression erst ab 30 Aufzeichnungen mit vollständigen Merkmalen.")
    return EvalReport(len(all_records), len(records), base_rate, per_label, terciles, coefficients, "\n".join(lines))


__all__ = [
    "append_record",
    "append_prefilter_record",
    "load_records",
    "update_outcomes",
    "evaluate",
    "EvalReport",
    "NUMERIC_FACTORS",
    "LABEL_PREFILTER",
    "ProfileCache",
]
