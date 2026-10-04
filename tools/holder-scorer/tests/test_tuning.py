"""Abstimmung 0.3.5 (OQ-032): Dev-Faktor monoton, WIDERRUF nach GO, wartende GO, Papier-Filter, Gate-Prüfung, Startbefehl."""
from __future__ import annotations

import dataclasses
import pathlib
from types import SimpleNamespace

from holder_scorer.collect import CreatorHistory, WalletProfile
from holder_scorer.encoding import b58encode
from holder_scorer.narrative import NameRegistry
from holder_scorer.paper import PaperTrader, Strategy
from holder_scorer.quick import QuickReport
from holder_scorer.replay import Outcome, _gate_line, diff_bootstrap, evaluate, format_report, gate_check
from holder_scorer.scoring import ScoringConfig, _dev
from tests.helpers import key
from tests.test_fair import GOOD_META, TIERS, _side_factory, _standard_flow, _with_meta
from tests.test_live import T0, launch_msg, make_engine, trade_logs


def test_dev_factor_is_monotone_and_zero_from_the_gate_limit():
    cfg = ScoringConfig()
    mx = cfg.w_dev

    def pts(buy: float, sold: float = 0.0) -> float:
        return _dev(SimpleNamespace(dev_buy_share=buy, dev_sold_share=sold, dev_holds_share=buy * (1 - sold)), cfg).points

    assert pts(0.0) == mx * 0.3 and pts(0.02) == mx and pts(0.03) == mx
    assert pts(0.02) > pts(0.05) > pts(0.08) > pts(0.10) == 0.0 == pts(0.12) == pts(0.27)
    assert abs(pts(0.065) - mx * 0.4) < 1e-9  # Mitte zwischen dev_small_buy 3 % und dev_big_hold 10 %
    assert abs(pts(0.02, sold=0.25) - mx * 0.5) < 1e-9 and pts(0.02, sold=0.6) == 0.0
    value = dataclasses.astuple(_dev(SimpleNamespace(dev_buy_share=0.12, dev_sold_share=0.0, dev_holds_share=0.12), cfg))[3]
    assert "Fair-Gate" in value
    assert "dev_small_buy" in dataclasses.asdict(cfg)  # Knickpunkt steht in der Konfiguration und damit im Regel-Hash


def test_copycat_check_is_directional():
    reg = NameRegistry()
    reg.register("first", "Tiffany Blue", "TIFF", 100.0)
    reg.register("second", "Tiffany Blue", "TIFF", 100.0)  # gleiche Sekunde: Reihenfolge entscheidet
    assert not reg.is_copycat("first", "Tiffany Blue", "TIFF", 101.0)
    assert reg.is_copycat("second", "Tiffany Blue", "TIFF", 101.0)
    assert reg.is_copycat("unregistered", "Tiffany Blue", "TIFF", 101.0)  # unbekannter Mint: gegen alles geprüft
    assert not reg.is_copycat("first", "Tiffany Blue", "TIFF", 100.0 + 3601)  # nach einer Stunde vergessen


def test_widerruf_after_go_when_the_dev_sells_a_little_and_rug_still_follows():
    engine, alerts = make_engine(stufe=2, tiers=TIERS)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]
    engine.on_logs(b58encode(mint), 5200, "devsell", None, trade_logs(mint, creator, 0.05, 2_000_000.0, False, int(T0 + 30), creator), now=T0 + 30)
    engine.tick(T0 + 31)
    assert [a.tier for a in alerts] == ["BLICK", "GO", "WIDERRUF"] and "nach GO · Dev verkauft 10 %" in alerts[2].text
    engine.tick(T0 + 37)
    assert [a.tier for a in alerts] == ["BLICK", "GO", "WIDERRUF"]  # einmal je Token
    engine.on_logs(b58encode(mint), 5300, "devdump", None, trade_logs(mint, creator, 0.5, 18_000_000.0, False, int(T0 + 40), creator), now=T0 + 40)
    engine.tick(T0 + 41)
    assert [a.tier for a in alerts] == ["BLICK", "GO", "WIDERRUF", "RUG"] and "DEV-DUMP" in alerts[3].text


def test_go_waiting_for_metadata_is_counted_not_locked():
    hist = CreatorHistory(address="c", prior_tokens=2, graduated=1, source="rpc")
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=_side_factory(hist, WalletProfile(address="c", tx_count=400), None, skip_metadata=True))
    engine.rpc = object()
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK"] and engine.stats["go_wartet"] == 1 and engine.stats.get("gesperrt", 0) == 0
    engine.tick(T0 + 31)
    assert engine.stats["go_wartet"] == 1  # einmal je Token
    # kommen die Metadaten doch noch, folgt das GO ohne Sperre
    engine.apply_metadata(engine.tokens[b58encode(mint)], GOOD_META, T0 + 32)
    engine.tick(T0 + 36)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]


def test_paper_filter_respects_the_fairness_gate():
    engine, _ = make_engine(stufe=2, tiers=TIERS)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    state = engine.tokens[b58encode(mint)]
    report = QuickReport(mint=state.mint, word="WARTE", phase="curve", score=50.0)
    strat = Strategy("TEST-früh", "FRÜH", tp=2.0, sl=0.5, description="t")
    state.fair = {"ok": False, "hard_ok": False, "fails": ["Dev verkauft 10 %"], "hard_fails": ["Dev verkauft 10 %"], "pending": [], "values": {}}
    strict = PaperTrader([strat])
    strict.attach(engine)
    strict._consider(state, report, None, T0 + 5, "FRÜH")
    assert strict.orders == [] and strict._filters_ok(strat, strict.last_info[state.mint], state) == (False, "unfair: Dev verkauft 10 %")
    loose = PaperTrader([strat], fair_filter=False)
    loose.attach(engine)
    loose._consider(state, report, None, T0 + 5, "FRÜH")
    assert len(loose.orders) == 1
    state.fair["hard_ok"] = True
    strict._consider(state, report, None, T0 + 6, "FRÜH")
    assert len(strict.orders) == 1


def _oc(mint: str, tier: str, r: float, block: int) -> Outcome:
    return Outcome(mint=mint, tier=tier, latency_s=30.0, horizon_s=300.0, t_alert=0.0, t_entry=30.0, t_exit=330.0, entry_mc_sol=30.0, exit_mc_sol=30.0, graduated=False, r_opt=r, r_cons=r, trades_between=1, block=block)


def test_gate_check_compares_go_with_gesperrt():
    outcomes = [_oc(f"G{i}", "GO", 0.1 + 0.02 * (i % 3), 1 + i % 4) for i in range(12)] + [_oc(f"S{i}", "GESPERRT", -0.2 + 0.01 * (i % 3), 1 + i % 4) for i in range(12)]
    g = gate_check(outcomes)
    assert g["go"]["n"] == 12 and g["gesperrt"]["n"] == 12 and g["diff"] > 0.25 and g["boot"]["lo"] > 0 and g["lesart"].startswith("Sperre richtig")
    line = _gate_line(g)
    assert line.startswith("Gate-Prüfung (GO gegen GESPERRT, +30 s / +300 s)") and "Sperre richtig" in line
    flipped = gate_check([_oc(f"G{i}", "GO", -0.2, 1 + i % 4) for i in range(8)] + [_oc(f"S{i}", "GESPERRT", 0.2, 1 + i % 4) for i in range(8)])
    assert flipped["lesart"].startswith("Sperre unnötig")
    only_go = gate_check([o for o in outcomes if o.tier == "GO"])
    assert "keine GESPERRT-Records" in only_go["lesart"] and _gate_line(only_go).endswith("(Aufzeichnung, keine Nachricht).")
    assert diff_bootstrap([(0.1, True, 1), (0.0, False, 1)]) is None  # eine Stunde reicht nicht für ein Intervall
    report = evaluate([], {})
    assert "gate_check" in report and "Gate-Prüfung" in format_report(report)


def test_readme_start_commands_record_gesperrt():
    text = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    cmds = [line for line in text.splitlines() if "python -m holder_scorer live" in line and "--tiers " in line]
    assert cmds and all("gesperrt" in line for line in cmds)
