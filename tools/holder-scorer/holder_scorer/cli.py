"""Command line interface: score, watch, outcome, evaluate, selftest, legend."""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import make_rpc
from .calibrate import append_prefilter_record, append_record, evaluate, update_outcomes
from .collect import collect
from .features import compute_features
from .notify import format_legend, format_short, send_telegram, telegram_configured
from .quick import QuickConfig, QuickReport, quick_check
from .rpc import RpcError
from .scoring import ScoringConfig, format_verdict

NOTIFY_DEFAULT = "go"


def _config_from_args(args: argparse.Namespace) -> ScoringConfig:
    cfg = ScoringConfig.early() if getattr(args, "early", False) else ScoringConfig()
    if getattr(args, "min_age", None) is not None:
        cfg.min_age_s = args.min_age
    if getattr(args, "yes_threshold", None) is not None:
        cfg.yes_threshold = args.yes_threshold
    if getattr(args, "no_threshold", None) is not None:
        cfg.no_threshold = args.no_threshold
    return cfg


def _quick_from_args(args: argparse.Namespace) -> QuickConfig:
    return QuickConfig(fast=bool(getattr(args, "fast", False) or getattr(args, "early", False)), use_market=not getattr(args, "no_market", False))


def _add_rpc_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rpc", help="Solana-RPC-URL (oder Umgebungsvariable SOLANA_RPC_URL)")
    p.add_argument("--rps", type=float, help="Anfragen pro Sekunde (Standard 10, Helius-Gratis-Tarif)")


def _add_score_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--early", action="store_true", help="Früh-Modus: Urteil ab 20 s Alter mit kleineren Mindestmengen, weniger Abfragen")
    p.add_argument("--fast", action="store_true", help="weniger Transaktionen und Wallet-Profile laden (schneller, etwas weniger genau)")
    p.add_argument("--no-market", action="store_true", help="keine Marktzahlen von DexScreener abrufen")
    p.add_argument("--min-age", type=float, help="Mindestalter in Sekunden, darunter Urteil FRÜH (Standard 90, mit --early 20)")
    p.add_argument("--yes-threshold", type=float, help="Score ab dem das Urteil GO lautet (Standard 65)")
    p.add_argument("--no-threshold", type=float, help="Score unter dem das Urteil NEIN lautet (Standard 45)")
    p.add_argument("--telegram", action="store_true", help="Kurznachricht per Telegram senden (TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID)")


def _stats_line(rpc) -> str:
    by = rpc.stats.get("by_method", {})
    top = ", ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:4])
    return f"{rpc.stats['requests']} Request-Einheiten in {rpc.stats['posts']} HTTP-Aufrufen, {rpc.stats['retries']} Wiederholungen ({top})"


def _record_report(path: str, report: QuickReport) -> None:
    if report.verdict is None:
        return
    extra = {"word": report.word, "flags": report.flags, "market": report.market.to_dict() if report.market else None, "sol_usd": report.sol_usd}
    append_record(path, report.verdict, extra)


def _notify(report: QuickReport, words: set[str]) -> None:
    if report.word in words:
        ok = send_telegram(format_short(report))
        if not ok:
            print("(Telegram-Versand fehlgeschlagen)", file=sys.stderr)


def cmd_score(args: argparse.Namespace) -> int:
    rpc = make_rpc(args.rpc, args.rps)
    cfg = _config_from_args(args)
    t0 = time.monotonic()
    try:
        report = quick_check(args.mint, rpc, config=cfg, quick=_quick_from_args(args))
    except RpcError as exc:
        print(f"RPC-Fehler: {exc}", file=sys.stderr)
        return 2
    if args.record:
        _record_report(args.record, report)
    if args.telegram:
        if not telegram_configured():
            print("Telegram nicht konfiguriert: TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID setzen", file=sys.stderr)
        else:
            _notify(report, {report.word})
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    elif args.long and report.verdict is not None:
        print(format_short(report))
        print()
        print(format_verdict(report.verdict))
        print(f"\n({time.monotonic() - t0:.1f} s, {_stats_line(rpc)})")
    else:
        print(format_short(report))
        if args.long:
            print("\n(keine Curve-Analyse für diesen Token, nur Marktzahlen)")
    return 0 if report.buy_signal else 1


def cmd_outcome(args: argparse.Namespace) -> int:
    rpc = make_rpc(args.rpc, args.rps)
    n = update_outcomes(args.file, rpc, horizon_s=args.horizon, growth_target=args.target)
    print(f"{n} Aufzeichnungen nachgeprüft ({_stats_line(rpc)})")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    print(evaluate(args.file).text)
    return 0


def cmd_legend(args: argparse.Namespace) -> int:
    print(format_legend())
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    from .watch import watch

    rpc = make_rpc(args.rpc, args.rps)
    cfg = _config_from_args(args)
    notify_words = {w.strip().upper() for w in (args.notify or NOTIFY_DEFAULT).split(",") if w.strip()}
    if args.telegram and not telegram_configured():
        print("Telegram nicht konfiguriert: TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID setzen", file=sys.stderr)
        return 2
    delay = args.delay if args.delay is not None else (25.0 if args.early else 90.0)

    def on_report(r: QuickReport):
        if r.score is None or r.score >= args.min_score or r.flags:
            print(f"\n{time.strftime('%H:%M:%S')}  {r.mint}")
            print(format_short(r))
            if args.verbose and r.verdict is not None:
                print(format_verdict(r.verdict))
        if args.record:
            _record_report(args.record, r)
        if args.telegram:
            _notify(r, notify_words)

    def on_skip(mint: str, signatures: int):
        if args.record:
            append_prefilter_record(args.record, mint, signatures)

    watch(
        rpc,
        delay,
        on_report,
        config=cfg,
        quick=_quick_from_args(args),
        max_lateness=args.max_lag,
        min_trades=args.min_trades,
        max_per_hour=args.max_per_hour,
        on_skip=on_skip,
    )
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    from .live import LiveConfig, live

    rpc = make_rpc(args.rpc, args.rps)
    config, scoring = LiveConfig.for_stufe(args.stufe)
    if args.track is not None:
        config.track_seconds = args.track
    config.commitment = args.commitment
    config.include_link = not args.no_link
    config.fetch_missing_events = not args.no_fetch
    if args.no_side:
        config.creator_scan_min_buyers = 10**9
        config.profiles_min_buyers = 10**9
        config.fetch_create_tx = False
    if args.min_age is not None:
        scoring.min_age_s = args.min_age
    if args.yes_threshold is not None:
        scoring.yes_threshold = args.yes_threshold
    if args.blick_buyers is not None:
        config.blick_min_outside_buyers = args.blick_buyers
    if args.blick_inflow is not None:
        config.blick_min_inflow_sol = args.blick_inflow
    if args.budget is not None:
        config.rpc_units_per_hour = args.budget
    tiers = tuple(t.strip().upper() for t in (args.tiers or "blick,go,widerruf,rug,gesperrt").split(",") if t.strip())
    notify_words = {w.strip().upper() for w in (args.notify or "blick,go,widerruf,rug").split(",") if w.strip()}
    # fairness gate (fair.py): the principles of docs/fair_launch.md as conditions for BLICK and GO
    config.fair.enabled = not getattr(args, "no_fair", False)
    if getattr(args, "fair_dev_max", None) is not None:
        config.fair.max_dev_share = args.fair_dev_max
    if getattr(args, "fair_socials", None) is not None:
        config.fair.min_socials = args.fair_socials
    if getattr(args, "fair_ohne_historie", False):
        config.fair.require_creator_check = False
    watch = tuple(w.strip() for w in (getattr(args, "beobachte", None) or "").split(",") if w.strip())
    config.watch_terms = watch
    if watch:
        # an explicit watch list always alerts and always notifies, whatever the tier selection says
        tiers = tiers if "WATCH" in tiers else tiers + ("WATCH",)
        notify_words.add("WATCH")
    config.tiers = tiers
    if args.telegram and not telegram_configured():
        print("Telegram nicht konfiguriert: TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID setzen", file=sys.stderr)
        return 2

    sender = None
    if args.telegram:
        from .notify import TelegramSender

        sender = TelegramSender()

    def send_async(text: str) -> None:
        # one background queue: alerts keep their order, 429/network errors are retried, losses are counted
        if sender is not None:
            sender.send(text)

    from . import __version__
    from .calibrate import alert_record_extra, rules_hash

    config.tape_path = getattr(args, "tape", None)
    config.tape_sample = float(getattr(args, "tape_sample", 0.0) or 0.0)
    if config.tape_sample and not config.tape_path:
        print("--tape-sample braucht --tape", file=sys.stderr)
        return 2
    # precision gate: holder rise in the last seconds, similarity to the saved good coins (profile.py)
    if getattr(args, "holder_anstieg", None) is not None:
        config.blick_min_holder_rise = config.go_min_holder_rise = args.holder_anstieg
    if getattr(args, "profil_min", None) is not None:
        config.profile_min_similarity = args.profil_min
    config.profile_required = bool(getattr(args, "profil_pflicht", False))
    profile_line = ""
    if getattr(args, "profil", None):
        from .profile import load_profile

        try:
            prof = load_profile(args.profil)
        except (OSError, ValueError) as exc:
            print(f"Profil nicht ladbar: {exc}", file=sys.stderr)
            return 2
        config.profile_path = args.profil
        profile_line = f" · Profil {prof['hash']} ({len(prof.get('good') or [])} gut / {len(prof.get('bad') or [])} schlecht, Schwelle {config.profile_min_similarity:.2f})"
    elif config.profile_required:
        print("--profil-pflicht braucht --profil", file=sys.stderr)
        return 2
    rules = rules_hash(config, scoring, __version__)
    print(
        f"Regelversion {__version__} · Regel-Hash {rules}"
        + (f" · Tape {config.tape_path}" if config.tape_path else "")
        + (f" · Kontroll-Stichprobe {config.tape_sample:.0%}" if config.tape_sample else "")
        + f" · Halter-Anstieg ≥ {config.go_min_holder_rise} in {config.holder_rise_window_s:.0f} s"
        + profile_line
        + (f" · Beobachtungsliste: {', '.join(watch)}" if watch else "")
        + f" · Fair-Gate: {config.fair.summary()}"
    )

    def on_alert(alert):
        print(f"\n{time.strftime('%H:%M:%S')}  {alert.tier}")
        print(alert.text)
        if args.record and alert.report.verdict is not None:
            append_record(args.record, alert.report.verdict, alert_record_extra(alert, args.stufe, rules, __version__, config, scoring))
        if args.telegram and alert.tier in notify_words:
            send_async(alert.text)

    paper = None
    if args.paper:
        from .narrative import load_keywords
        from .paper import PaperTrader, strategies_by_name

        strategies = strategies_by_name((args.paper_strategies or "alle").split(","))
        message_strategies = [s.strip() for s in (args.paper_telegram or "").split(",") if s.strip()]
        if message_strategies and not args.telegram:
            print("--paper-telegram braucht --telegram", file=sys.stderr)
            return 2
        paper = PaperTrader(
            strategies,
            size_sol=args.paper_size,
            latency_s=args.paper_latency,
            record_path=args.paper,
            on_message=send_async if args.telegram else None,
            message_strategies=message_strategies,
            keywords=load_keywords(args.narratives),
            fair_filter=not getattr(args, "paper_ohne_fair", False),
        )
        print(f"Papier-Trading: {len(strategies)} Strategien, {args.paper_size} SOL je Trade, Latenz {args.paper_latency:.0f} s, Aufzeichnung in {args.paper}")

    live(rpc, config, scoring, on_alert, ws_url=args.ws, paper=paper)
    if paper is not None:
        print(paper.status_line())
    if sender is not None:
        sender.close()
        print(sender.status_line())
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    from .paper import STRATEGIES, load_paper, look_back, paper_report, parse_calls_file

    if args.paper_cmd == "strategien":
        for s in STRATEGIES:
            print(f"{s.name:<14} {s.description}")
        return 0
    if args.paper_cmd == "report":
        records = load_paper(args.file)
        print(paper_report(records, cash=args.kasse if args.kasse > 0 else None, size=args.einsatz))
        return 0
    if args.paper_cmd == "rueckblick":
        calls = parse_calls_file(args.file)
        if not calls:
            print("keine Calls gefunden: je Zeile <Mint> <Unix-Zeit oder ISO-Zeit>", file=sys.stderr)
            return 2
        rpc = make_rpc(args.rpc, args.rps)
        print(look_back(rpc, calls, size_sol=args.einsatz or 0.08, latency_s=args.latenz, horizon_s=args.horizont))
        print(_stats_line(rpc))
        return 0
    return 2


def cmd_tape(args: argparse.Namespace) -> int:
    from .replay import DEFAULT_HORIZONS, DEFAULT_LATENCIES, Costs, report_to_json, tape_report

    def floats(text: str | None, default: tuple[float, ...]) -> tuple[float, ...]:
        if not text:
            return default
        return tuple(float(x) for x in text.split(",") if x.strip())

    costs = Costs.scenario(args.priority)
    if args.ata_rent is not None:
        costs = Costs(base_fee=costs.base_fee, cu_limit=costs.cu_limit, cu_price_micro=costs.cu_price_micro, ata_rent=args.ata_rent, close_account=costs.close_account)
    text, report = tape_report(
        args.records,
        args.tape,
        size_sol=args.einsatz,
        latencies=floats(args.latenz, DEFAULT_LATENCIES),
        horizons=floats(args.horizont, DEFAULT_HORIZONS),
        costs=costs,
        k_controls=args.kontrollen,
        tiers=[t.strip() for t in args.tiers.split(",")] if args.tiers else None,
    )
    print(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(report_to_json(report))
        print(f"JSON nach {args.json} geschrieben")
    return 0


def cmd_profil(args: argparse.Namespace) -> int:
    from .profile import MIN_GOOD, build_profile, describe_profile, load_profile, parse_mints_file, profile_usable, save_profile
    from .replay import Costs

    if args.profil_cmd == "zeigen":
        print(describe_profile(load_profile(args.file)))
        return 0
    if args.profil_cmd != "bauen":
        return 2
    mints = parse_mints_file(args.mints) if args.mints else []
    if not (args.tape or args.records or args.papier or mints):
        print("mindestens eine Quelle angeben: --tape, --records, --papier oder --mints", file=sys.stderr)
        return 2
    rpc = None
    if mints:
        todo = min(len(mints), args.max_mints)
        # getSignaturesForAddress je Seite plus getTransaction je Trade im Fenster: Obergrenze vorab, Istwert danach
        print(f"RPC-Schätzung für {todo} Mints: bis zu {todo * args.max_pages} Signatur-Seiten und einige hundert getTransaction je Mint (Obergrenze {todo * args.max_pages * 1000} Einheiten)")
        if args.dry_run:
            return 0
        rpc = make_rpc(args.rpc, args.rps)
    elif args.dry_run:
        print("Trockenlauf ohne Mint-Liste: nur Dateien, keine RPC-Aufrufe nötig")
    profile, text = build_profile(
        tape_path=args.tape,
        records_path=args.records,
        paper_path=args.papier,
        mints=mints,
        rpc=rpc,
        entry_age_s=args.einstieg,
        horizon_s=args.horizont,
        size_sol=args.einsatz,
        costs=Costs.scenario(args.priority),
        quantile=args.quantil,
        split=args.split,
        max_mints=args.max_mints,
        max_pages=args.max_pages,
    )
    print(text)
    if rpc is not None:
        print(_stats_line(rpc))
    if not profile_usable(profile):
        print(f"Kein Profil geschrieben (weniger als {MIN_GOOD} gute Coins mit Vektor).", file=sys.stderr)
        return 1
    save_profile(profile, args.out)
    print(f"Profil nach {args.out} geschrieben (Hash {profile['hash']}). Start: live --profil {args.out}")
    return 0


def cmd_dex(args: argparse.Namespace) -> int:
    from .dexpaid import DexWatcher, dex_report

    if args.dex_cmd == "beobachten":
        watcher = DexWatcher(out_path=args.out, chain=args.kette, poll_s=args.intervall)
        print(f"DexScreener-Beobachter (record-only, kein Kauf): Feeds alle {args.intervall:.0f} s, Preise bei +0/+5/+15/+60 min, Ausgabe {args.out}")
        watcher.run(duration_s=args.dauer)
        print(watcher.status_line())
        return 0
    if args.dex_cmd == "report":
        text, report = dex_report(args.file, records_path=args.records, fee_bps=args.gebuehr_bps)
        print(text)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=1)
            print(f"JSON nach {args.json} geschrieben")
        return 0
    return 2


def cmd_launch(args: argparse.Namespace) -> int:
    from .launchplan import DEFAULT_DEV_BUYS, DEFAULT_SALE_SHARES, format_table, table

    def floats(text: str | None, default: tuple[float, ...]) -> tuple[float, ...]:
        return default if not text else tuple(float(x) for x in text.split(",") if x.strip())

    rows = table(floats(args.dev_kauf, DEFAULT_DEV_BUYS), floats(args.verkauf, DEFAULT_SALE_SHARES), volume_multiple=args.volumen_faktor, holder_rewards=args.holder_rewards)
    print(format_table(rows))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        print(f"JSON nach {args.json} geschrieben")
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
    print(f"\nMerkmale: age={feats.age_s and round(feats.age_s)} holders={feats.holders_now} growth60={feats.holder_growth_60s} mc_sol={feats.mc_sol}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="holder_scorer", description="Bewertet, ob ein pump.fun-Token wahrscheinlich mehr Holder bekommt.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="einen Token jetzt bewerten (Kurznachricht)")
    s.add_argument("mint")
    s.add_argument("--long", action="store_true", help="zusätzlich die vollständige Faktor-Tabelle ausgeben")
    s.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben (für andere Programme)")
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
    w.add_argument("--delay", type=float, help="Sekunden nach dem Start bis zur Bewertung (Standard 90, mit --early 25)")
    w.add_argument("--max-lag", type=float, default=30.0, help="Token überspringen, die mehr als N s nach der Fälligkeit dran wären (Standard 30)")
    w.add_argument("--min-trades", type=int, default=6, help="Vorfilter: mindestens N Transaktionen, sonst keine Bewertung (Standard 6)")
    w.add_argument("--max-per-hour", type=float, help="höchstens N Launches pro Stunde bewerten (schont das Kontingent)")
    w.add_argument("--min-score", type=float, default=0.0, help="nur Urteile ab diesem Score anzeigen (Warnungen immer)")
    w.add_argument("--notify", help="welche Urteile per Telegram gehen, kommagetrennt (Standard: go; z. B. go,rug)")
    w.add_argument("--record", help="alle Urteile an diese JSONL-Datei anhängen")
    w.add_argument("--verbose", action="store_true", help="zusätzlich die vollständige Faktor-Tabelle je Token")
    _add_rpc_args(w)
    _add_score_args(w)
    w.set_defaults(func=cmd_watch)

    lv = sub.add_parser("live", help="Live-Modus: Trades aus den Logs, Alarme BLICK/GO/RUG so früh wie möglich")
    lv.add_argument("--stufe", type=int, choices=(1, 2, 3), default=2, help="1 vorsichtig, 2 Standard, 3 aggressiv (mehr Calls, mehr Fehlalarme)")
    lv.add_argument("--tiers", help="welche Alarme erzeugt und aufgezeichnet werden, kommagetrennt (Standard blick,go,widerruf,rug,gesperrt)")
    lv.add_argument("--notify", help="welche Alarme per Telegram gehen (Standard blick,go,widerruf,rug; GESPERRT nur mit Nennung)")
    lv.add_argument("--telegram", action="store_true", help="Alarme per Telegram senden")
    lv.add_argument("--record", help="Alarme samt Merkmalen, Slot, Kurvenstand und Regelversion an diese JSONL-Datei anhängen (für outcome/evaluate)")
    lv.add_argument("--tape", metavar="DATEI", help="jeden gesehenen Trade eines Tokens mit Alarm an diese JSONL-Datei anhängen (Nachrechnen ohne getTransaction)")
    lv.add_argument("--tape-sample", type=float, default=0.0, metavar="ANTEIL", help="zusätzlich diesen Anteil aller beobachteten Token (0–1, z. B. 0.1) ab dem ersten Trade mitschreiben: Kontrollgruppe für 'tape report'")
    lv.add_argument("--track", type=float, help="Sekunden, die ein Token beobachtet wird (Standard 240)")
    lv.add_argument("--commitment", choices=("processed", "confirmed"), default="confirmed", help="processed ist einen Tick schneller, confirmed sicherer")
    lv.add_argument("--ws", help="Websocket-URL des RPC (Standard: aus der RPC-URL abgeleitet)")
    lv.add_argument("--no-side", action="store_true", help="keine Hintergrundabfragen (Creator, Wallets, Create-Transaktion): null RPC-Last, weniger Warnungen")
    lv.add_argument("--no-fetch", action="store_true", help="Logs ohne Event nicht per getTransaction nachladen")
    lv.add_argument("--no-link", action="store_true", help="keine pump.fun-Link-Zeile in den Nachrichten")
    lv.add_argument("--min-age", type=float, help="Mindestalter für GO in Sekunden")
    lv.add_argument("--yes-threshold", type=float, help="Score ab dem GO gilt (Notlösung gegen Fehlalarme: 75)")
    lv.add_argument("--blick-buyers", type=int, help="Außen-Käufer, ab denen BLICK kommt (Stufe: 8 / 5 / 3)")
    lv.add_argument("--blick-inflow", type=float, help="organischer Zufluss in SOL, ab dem BLICK kommt (Stufe: 1,0 / 0,5 / 0,25)")
    lv.add_argument("--budget", type=float, help="RPC-Einheiten pro Stunde für Hintergrundabfragen (Standard 4000, etwa 100.000 Helius-Credits am Tag)")
    lv.add_argument("--profil", metavar="DATEI", help="Referenzprofil guter Coins aus 'profil bauen': GO nur bei Ähnlichkeit ≥ --profil-min (null zusätzliche RPC-Aufrufe)")
    lv.add_argument("--profil-min", type=float, help="Mindest-Ähnlichkeit 0–1 für GO (Standard 0,7)")
    lv.add_argument("--profil-pflicht", action="store_true", help="ohne nutzbares Profil kein GO")
    lv.add_argument("--holder-anstieg", type=int, help="neue Halter (ohne Dev) in den letzten 15 s, die BLICK und GO brauchen (Stufe 1: 3, sonst 2)")
    lv.add_argument("--beobachte", metavar="BEGRIFFE", help="Beobachtungsliste, kommagetrennt (z. B. TIFFANY): sofort 👁️ WATCH, wenn Name, Symbol oder Beschreibung eines Launches den Begriff enthält; unabhängig von --tiers/--notify")
    lv.add_argument("--no-fair", action="store_true", help="Fairness-Gate ausschalten (Standard an: Dev-Anteil, Dev-Verkauf, Bundle-Wallets, Kopie, Historie, Bots, Metadaten als Bedingung für BLICK/GO)")
    lv.add_argument("--fair-dev-max", type=float, help="höchster Dev-Anteil an der Supply für einen Call (Stufe 1: 0,05, 2: 0,07, 3: 0,10)")
    lv.add_argument("--fair-socials", type=int, help="Mindestzahl Social-Links in den Metadaten für GO (Stufe 1/2: 2, 3: 1)")
    lv.add_argument("--fair-ohne-historie", action="store_true", help="GO nicht auf die geladene Creator-Historie warten lassen")
    lv.add_argument("--paper", metavar="DATEI", help="Papier-Trading: alle Strategien handeln jeden Call ohne Geld, jede Entscheidung landet in dieser JSONL-Datei")
    lv.add_argument("--paper-size", type=float, default=0.08, help="SOL je Papier-Trade (Standard 0,08)")
    lv.add_argument("--paper-latency", type=float, default=2.0, help="Sekunden zwischen Entscheidung und Ausführung (Standard 2)")
    lv.add_argument("--paper-strategies", help="welche Strategien, kommagetrennt (Standard alle; Liste: paper strategien)")
    lv.add_argument("--paper-telegram", help="Papier-Käufe und -Verkäufe dieser Strategien per Telegram melden (kommagetrennt)")
    lv.add_argument("--narratives", metavar="DATEI", help="Trend-Wörter für den Narrativ-Score, eines je Zeile")
    lv.add_argument("--paper-ohne-fair", action="store_true", help="Papier-Strategien dürfen auch Coins kaufen, die das Fairness-Gate sperrt (nur zum Vergleich)")
    _add_rpc_args(lv)
    lv.set_defaults(func=cmd_live)

    pp = sub.add_parser("paper", help="Papier-Trading auswerten: report, strategien, rueckblick")
    pps = pp.add_subparsers(dest="paper_cmd", required=True)
    pr = pps.add_parser("report", help="Ergebnis je Strategie aus der Papier-Datei, mit Was-wäre-wenn auf den Preispfaden")
    pr.add_argument("file")
    pr.add_argument("--kasse", type=float, default=0.25, help="Kasse in SOL für die Nachrechnung mit begrenztem Geld (0 = aus)")
    pr.add_argument("--einsatz", type=float, help="SOL je Trade für die Kassen-Nachrechnung (Standard: wie gehandelt)")
    pr.set_defaults(func=cmd_paper)
    ps = pps.add_parser("strategien", help="die eingebauten Strategien auflisten")
    ps.set_defaults(func=cmd_paper)
    pb = pps.add_parser("rueckblick", help="frühere Calls (Datei mit <Mint> <Zeit> je Zeile) aus der Kette nachrechnen")
    pb.add_argument("file")
    pb.add_argument("--einsatz", type=float, default=0.08, help="SOL je Trade (Standard 0,08)")
    pb.add_argument("--latenz", type=float, default=2.0, help="Sekunden zwischen Call und Kauf (Standard 2)")
    pb.add_argument("--horizont", type=float, default=900.0, help="Sekunden nach dem Call, die betrachtet werden (Standard 900)")
    _add_rpc_args(pb)
    pb.set_defaults(func=cmd_paper)

    tp = sub.add_parser("tape", help="Alarme aus Records + Tape nachrechnen: Netto-Rendite je Latenz/Horizont, Kontrollgruppe, Bootstrap")
    tps = tp.add_subparsers(dest="tape_cmd", required=True)
    tr_ = tps.add_parser("report", help="Replay der Alarme (Paper-only): Einstieg L s nach Alarm, Ausstieg nach H s, Kosten, Kontrollgruppe")
    tr_.add_argument("records", help="Record-Datei aus 'live --record' (ab 0.3.1)")
    tr_.add_argument("tape", help="Tape-Datei aus 'live --tape' (mit --tape-sample für die Kontrollgruppe)")
    tr_.add_argument("--einsatz", type=float, default=0.08, help="SOL je Trade (Standard 0,08)")
    tr_.add_argument("--latenz", help="Einstiegs-Latenzen in Sekunden, kommagetrennt (Standard 2,10,30,60)")
    tr_.add_argument("--horizont", help="Haltedauern in Sekunden, kommagetrennt (Standard 60,300,900)")
    tr_.add_argument("--priority", choices=("low", "medium", "high"), default="medium", help="Priority-Fee-Szenario (Standard medium)")
    tr_.add_argument("--ata-rent", type=int, help="Token-Account-Einlage in Lamports (Standard 2039280, NICHT VERIFIZIERT – per RPC prüfen)")
    tr_.add_argument("--kontrollen", type=int, default=5, help="Kontroll-Token je Alarm (Standard 5)")
    tr_.add_argument("--tiers", help="nur diese Alarmstufen, kommagetrennt (Standard alle)")
    tr_.add_argument("--json", metavar="DATEI", help="vollständiges Ergebnis zusätzlich als JSON schreiben")
    tr_.set_defaults(func=cmd_tape)

    pf = sub.add_parser("profil", help="Referenzprofil guter Coins: bauen aus Tape/Records/Papier/Mints, zeigen")
    pfs = pf.add_subparsers(dest="profil_cmd", required=True)
    pb_ = pfs.add_parser("bauen", help="Frühvektoren und Rendite-Labels aus gespeicherten Coins, Bänder je Checkpoint, Zeitsplit-Prüfung")
    pb_.add_argument("--tape", metavar="DATEI", help="Tape aus 'live --tape' (beste Quelle: Vektor und Label aus denselben Trades)")
    pb_.add_argument("--records", metavar="DATEI", help="Records aus 'live --record' (ab 0.3.2 mit Vektoren)")
    pb_.add_argument("--papier", metavar="DATEI", help="Papier-Datei aus 'live --paper' (Label aus dem Papier-Ergebnis, wenn kein Tape-Label existiert)")
    pb_.add_argument("--mints", metavar="DATEI", help="Mint-Liste '<Mint> [gut|schlecht]' je Zeile; Historie per RPC (begrenzt durch --max-mints/--max-pages)")
    pb_.add_argument("--out", required=True, metavar="DATEI", help="Zieldatei des Profils (JSON), für 'live --profil'")
    pb_.add_argument("--einstieg", type=float, default=60.0, help="Label: Einstieg in Sekunden nach dem ersten Trade (Standard 60; Checkpoints davor zählen)")
    pb_.add_argument("--horizont", type=float, default=180.0, help="Label: Haltedauer in Sekunden (Standard 180 = Ende des 240-s-Fensters)")
    pb_.add_argument("--einsatz", type=float, default=0.08, help="Label: SOL je Trade (Standard 0,08)")
    pb_.add_argument("--priority", choices=("low", "medium", "high"), default="medium", help="Label: Priority-Fee-Szenario (Standard medium)")
    pb_.add_argument("--quantil", type=float, default=0.10, help="Bandbreite: Perzentil q bis 1−q der guten Coins (Standard 0,10)")
    pb_.add_argument("--split", type=float, default=0.5, help="Zeitsplit-Prüfung: Anteil früher Coins zum Bauen, Rest zum Testen (Standard 0,5; 0 = aus)")
    pb_.add_argument("--max-mints", type=int, default=20, help="höchstens so viele Mints per RPC laden (Standard 20)")
    pb_.add_argument("--max-pages", type=int, default=10, help="höchstens so viele Signatur-Seiten je Mint (Standard 10 = 10 000 Signaturen)")
    pb_.add_argument("--dry-run", action="store_true", help="nur die RPC-Schätzung ausgeben, nichts laden")
    _add_rpc_args(pb_)
    pb_.set_defaults(func=cmd_profil)
    pz = pfs.add_parser("zeigen", help="ein Profil lesbar ausgeben (Bänder, Gewichte, Prüfung)")
    pz.add_argument("file")
    pz.set_defaults(func=cmd_profil)

    dx = sub.add_parser("dex", help="DexScreener-Bezahlsignale (Boosts, Enhanced Token Info) beobachten und als Call-Quelle messen (paper-only)")
    dxs = dx.add_subparsers(dest="dex_cmd", required=True)
    db = dxs.add_parser("beobachten", help="Feeds abfragen, Ereignisse und Preis-Schnappschüsse als JSONL schreiben (kein Schlüssel, 60/300 Anfragen je Minute)")
    db.add_argument("--out", required=True, metavar="DATEI", help="JSONL-Ausgabe (Ereignisse und Preise)")
    db.add_argument("--kette", default="solana", help="chainId (Standard solana)")
    db.add_argument("--intervall", type=float, default=60.0, help="Sekunden zwischen Feed-Abfragen (Standard 60)")
    db.add_argument("--dauer", type=float, help="nach so vielen Sekunden beenden (Standard: bis Strg+C)")
    db.set_defaults(func=cmd_dex)
    dr = dxs.add_parser("report", help="Follower-Rendite je Horizont aus der Beobachtungsdatei, Wilson/Bootstrap, Verknüpfung mit eigenen Records")
    dr.add_argument("file")
    dr.add_argument("--records", metavar="DATEI", help="Record-Datei aus 'live --record': welche eigenen Alarm-Coins zahlten später")
    dr.add_argument("--gebuehr-bps", type=int, default=50, help="Gebühr je Seite in Basispunkten (Standard 50, Annahme)")
    dr.add_argument("--json", metavar="DATEI", help="Ergebnis zusätzlich als JSON")
    dr.set_defaults(func=cmd_dex)

    la = sub.add_parser("launch", help="Launch-Rechner: Dev-Anteil, nötiger Fremdzufluss, Wert bei Graduation, Teilverkauf und Kursimpact (Kurvenmathematik, kein Kauf)")
    las = la.add_subparsers(dest="launch_cmd", required=True)
    lr = las.add_parser("rechner", help="Szenarien für Dev-Kauf × Verkaufsanteil ausgeben")
    lr.add_argument("--dev-kauf", help="Dev-Kauf in SOL, kommagetrennt (Standard 0,0.25,0.5,1,2,3,5)")
    lr.add_argument("--verkauf", help="Anteil der Dev-Token, der bei Graduation verkauft wird, kommagetrennt (Standard 0.25,0.5)")
    lr.add_argument("--volumen-faktor", type=float, default=2.0, help="Annahme: Kurvenvolumen bis Graduation = Faktor × Netto-Zufluss (Standard 2)")
    lr.add_argument("--holder-rewards", action="store_true", help="Coin mit Holder-Rewards: Creator-Fee geht an die Halter, nicht an den Dev")
    lr.add_argument("--json", metavar="DATEI", help="Szenarien zusätzlich als JSON")
    lr.set_defaults(func=cmd_launch)

    t = sub.add_parser("selftest", help="Datensammlung an einem echten Token prüfen")
    t.add_argument("mint")
    _add_rpc_args(t)
    t.set_defaults(func=cmd_selftest)

    lg = sub.add_parser("legend", help="die Kurzsprache der Nachrichten erklären")
    lg.set_defaults(func=cmd_legend)
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
