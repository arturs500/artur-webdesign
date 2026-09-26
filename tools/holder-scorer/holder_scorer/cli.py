"""Command line interface: score, outcome, evaluate, watch, selftest."""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import evaluate_token, make_rpc
from .calibrate import append_prefilter_record, append_record, evaluate, update_outcomes
from .collect import collect
from .features import compute_features
from .rpc import RpcError
from .scoring import ScoringConfig, format_verdict


def _config_from_args(args: argparse.Namespace) -> ScoringConfig:
    cfg = ScoringConfig()
    if getattr(args, "min_age", None) is not None:
        cfg.min_age_s = args.min_age
    if getattr(args, "yes_threshold", None) is not None:
        cfg.yes_threshold = args.yes_threshold
    if getattr(args, "no_threshold", None) is not None:
        cfg.no_threshold = args.no_threshold
    return cfg


def _add_rpc_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rpc", help="Solana-RPC-URL (oder Umgebungsvariable SOLANA_RPC_URL)")
    p.add_argument("--rps", type=float, help="Anfragen pro Sekunde (Standard 10, Helius-Gratis-Tarif)")


def _add_score_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben (für andere Programme)")
    p.add_argument("--no-deep", action="store_true", help="frühe Wallets nicht prüfen (spart etwa 15 Anfragen)")
    p.add_argument("--min-age", type=float, help="Mindestalter in Sekunden, darunter Urteil ZU_FRUEH (Standard 90)")
    p.add_argument("--yes-threshold", type=float, help="Score ab dem das Urteil JA lautet (Standard 65)")
    p.add_argument("--no-threshold", type=float, help="Score unter dem das Urteil NEIN lautet (Standard 45)")


def _stats_line(rpc) -> str:
    by = rpc.stats.get("by_method", {})
    top = ", ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:4])
    return f"{rpc.stats['requests']} Request-Einheiten in {rpc.stats['posts']} HTTP-Aufrufen, {rpc.stats['retries']} Wiederholungen ({top})"


def cmd_score(args: argparse.Namespace) -> int:
    rpc = make_rpc(args.rpc, args.rps)
    cfg = _config_from_args(args)
    t0 = time.monotonic()
    try:
        verdict = evaluate_token(args.mint, rpc=rpc, config=cfg, deep=not args.no_deep)
    except RpcError as exc:
        print(f"RPC-Fehler: {exc}", file=sys.stderr)
        return 2
    if args.record:
        append_record(args.record, verdict)
    if args.json:
        print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_verdict(verdict))
        print(f"\n({time.monotonic() - t0:.1f} s, {_stats_line(rpc)})")
    return 0 if verdict.buy_signal else 1


def cmd_outcome(args: argparse.Namespace) -> int:
    rpc = make_rpc(args.rpc, args.rps)
    n = update_outcomes(args.file, rpc, horizon_s=args.horizon, growth_target=args.target)
    print(f"{n} Aufzeichnungen nachgeprüft ({_stats_line(rpc)})")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    print(evaluate(args.file).text)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    from .watch import watch

    rpc = make_rpc(args.rpc, args.rps)
    cfg = _config_from_args(args)

    def on_verdict(v):
        if v.score >= args.min_score or v.hard_fails:
            print(f"\n{time.strftime('%H:%M:%S')}  {v.label:<9} {v.score:5.1f}  {v.mint}")
            if args.verbose:
                print(format_verdict(v))
        if args.record:
            append_record(args.record, v)

    def on_skip(mint: str, signatures: int):
        if args.record:
            append_prefilter_record(args.record, mint, signatures)

    watch(
        rpc,
        args.delay,
        on_verdict,
        config=cfg,
        deep=not args.no_deep,
        max_lateness=args.max_lag,
        min_trades=args.min_trades,
        max_per_hour=args.max_per_hour,
        on_skip=on_skip,
    )
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    rpc = make_rpc(args.rpc, args.rps)
    try:
        snap = collect(args.mint, rpc, deep=True)
    except RpcError as exc:
        print(f"RPC-Fehler: {exc}")
        return 2
    print(f"Bonding Curve: {snap.bonding_curve}")
    if snap.curve:
        c = snap.curve
        print(
            f"  complete={c.complete} progress={c.progress * 100:.1f}% real_quote={c.real_quote_reserves / 1e9:.3f} "
            f"creator={c.creator} quote_mint={c.quote_mint} mayhem={c.is_mayhem_mode}"
        )
    else:
        print("  Curve-Konto nicht gefunden oder nicht dekodierbar")
    if snap.create:
        ce = snap.create
        print(f"Create: {ce.name!r} {ce.symbol!r} user={ce.user} creator={ce.creator} slot={ce.slot} ts={ce.timestamp}")
        print(f"  uri={ce.uri}")
    else:
        print("Create-Event nicht gefunden (Historie unvollständig oder alter Token)")
    print(
        f"Signaturen: {snap.total_signatures} (fehlgeschlagen {snap.failed_tx}, nicht ladbar {snap.missing_tx}), "
        f"Trades dekodiert: {len(snap.trades)}, Historie vollständig: {snap.history_complete}"
    )
    for t in snap.trades[:3] + snap.trades[-3:]:
        print(
            f"  {'BUY ' if t.is_buy else 'SELL'} slot={t.slot} ts={t.timestamp} user={t.user[:8]}… "
            f"{t.quote_lamports / 1e9:.4f} SOL für {t.token_amount / 1e6:,.0f} Token ix={t.ix_name}"
        )
    print(f"Holder: {len(snap.holders) if snap.holders is not None else '?'} ({snap.holders_source})")
    print(f"Metadaten: {'ok' if snap.metadata_ok else 'fehlt'} {list(snap.metadata)[:8]}")
    if snap.creator_history:
        ch = snap.creator_history
        print(
            f"Creator: {ch.prior_tokens} frühere Token, {ch.graduated} graduiert, {ch.dead} tot, {ch.young} jung, "
            f"Quelle {ch.source}, {ch.coverage_note}"
        )
    print(f"Frühe Wallets geprüft: {len(snap.early_wallets)}, frisch: {sum(1 for w in snap.early_wallets if w.is_fresh)}")
    print("Hinweise: " + ("; ".join(snap.notes) if snap.notes else "keine"))
    print("Zeiten: " + ", ".join(f"{k} {v:.1f}s" for k, v in snap.timings.items()))
    print(_stats_line(rpc))
    feats = compute_features(snap)
    print(f"\nMerkmale: age={feats.age_s and round(feats.age_s)} holders={feats.holders_now} growth60={feats.holder_growth_60s}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="holder_scorer", description="Bewertet, ob ein pump.fun-Token wahrscheinlich mehr Holder bekommt.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="einen Token jetzt bewerten")
    s.add_argument("mint")
    s.add_argument("--record", help="Urteil samt Merkmalen an diese JSONL-Datei anhängen")
    _add_rpc_args(s)
    _add_score_args(s)
    s.set_defaults(func=cmd_score)

    o = sub.add_parser("outcome", help="für aufgezeichnete Token nachprüfen, ob die Holder gewachsen sind")
    o.add_argument("--file", required=True)
    o.add_argument("--horizon", type=float, default=900.0, help="Sekunden nach der Aufzeichnung (Standard 900)")
    o.add_argument("--target", type=float, default=1.5, help="Faktor, ab dem Holder-Wachstum als Erfolg zählt (Standard 1,5)")
    _add_rpc_args(o)
    o.set_defaults(func=cmd_outcome)

    e = sub.add_parser("evaluate", help="Trefferquoten und Faktor-Analyse aus der Aufzeichnung")
    e.add_argument("--file", required=True)
    e.set_defaults(func=cmd_evaluate)

    w = sub.add_parser("watch", help="neue Token live bewerten (braucht das Paket websockets)")
    w.add_argument("--delay", type=float, default=90.0, help="Sekunden nach dem Start bis zur Bewertung (Standard 90)")
    w.add_argument("--max-lag", type=float, default=30.0, help="Token überspringen, die mehr als N s nach der Fälligkeit dran wären (Standard 30)")
    w.add_argument("--min-trades", type=int, default=6, help="Vorfilter: mindestens N Transaktionen, sonst keine Bewertung (Standard 6)")
    w.add_argument("--max-per-hour", type=float, help="höchstens N Launches pro Stunde bewerten (schont das Kontingent)")
    w.add_argument("--min-score", type=float, default=0.0, help="nur Urteile ab diesem Score anzeigen")
    w.add_argument("--record", help="alle Urteile an diese JSONL-Datei anhängen")
    w.add_argument("--verbose", action="store_true", help="vollständige Faktor-Tabelle je Token")
    _add_rpc_args(w)
    _add_score_args(w)
    w.set_defaults(func=cmd_watch)

    t = sub.add_parser("selftest", help="Datensammlung an einem echten Token prüfen")
    t.add_argument("mint")
    _add_rpc_args(t)
    t.set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - never end with a traceback for the user
        print(f"Fehler: {exc!r}", file=sys.stderr)
        return 2
