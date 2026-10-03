"""Replay (Umbau P0): Rendite-Label aus Tape + Records, Kontrollgruppe, Statistik, Tape-Stichprobe im Live-Modus."""
from __future__ import annotations

import json

from holder_scorer import replay
from holder_scorer.cli import build_parser, cmd_tape
from holder_scorer.encoding import b58encode
from holder_scorer.paper import CURVE_FEE_BPS, buy_on_curve, sell_on_curve
from holder_scorer.replay import Costs, block_bootstrap, curve_from_row, evaluate, fee_bps_from_row, holm, simulate, tape_report, wilson
from tests.helpers import key
from tests.test_live import T0, feed_buyers, launch_msg, make_engine

V_SOL0 = 30_500_000_000  # 30 SOL virtual + 0.5 SOL dev buy
V_TOK0 = 1_073_000_000_000_000 - 20_000_000_000_000
R_TOK0 = 793_100_000_000_000 - 20_000_000_000_000


def row(ts: int, slot: int, v_sol: int = V_SOL0, v_tok: int = V_TOK0, r_tok: int = R_TOK0, sol: int = 100_000_000, control: bool = False, t0: float | None = None, mint: str = "M" * 44) -> dict:
    fee = sol * 95 // 10_000
    cfee = sol * 30 // 10_000
    return {
        "mint": mint, "seen_at": float(ts) + 0.8, "t0": t0 if t0 is not None else float(ts) - 5.0, "control": control, "backfill": False,
        "slot": slot, "ts": ts, "sig": f"sig{slot}", "buy": True, "user": "U" * 44, "sol": sol, "tok": 1_000_000_000_000,
        "vS": v_sol, "vT": v_tok, "rS": v_sol - 30_000_000_000, "rT": r_tok, "fee": fee, "creator_fee": cfee,
    }


def test_fee_bps_from_row_uses_logged_fees():
    assert fee_bps_from_row(row(1, 1, sol=1_000_000_000)) == 125
    assert fee_bps_from_row({"sol": 0, "fee": 5}) == CURVE_FEE_BPS
    assert fee_bps_from_row({"sol": 1_000, "fee": None}) == CURVE_FEE_BPS
    assert fee_bps_from_row({"sol": 1_000, "fee": 900, "creator_fee": 0}) == CURVE_FEE_BPS  # 9 000 bps: unplausibel


def test_simulate_flat_curve_loses_only_fees_and_costs():
    rows = [row(100, 10), row(300, 20)]
    costs = Costs()
    res = simulate(rows, t_entry=130.0, horizon_s=300.0, size_lamports=80_000_000, costs=costs)
    assert res is not None and not res["graduated"] and res["trades_between"] == 1
    tokens, sol_cost, _ = buy_on_curve(curve_from_row(rows[0]), 80_000_000, 125)
    proceeds, _ = sell_on_curve(curve_from_row(rows[1], d_sol=sol_cost, d_tok=tokens), tokens, 125)
    spent = 80_000_000 + 3 * costs.per_tx + costs.ata_rent
    expected = (proceeds + costs.ata_rent - spent) / spent
    assert abs(res["r_cons"] - expected) < 1e-12 and res["r_opt"] == res["r_cons"]
    assert -0.06 < res["r_cons"] < -0.02  # Gebühren, eigener Impact und Transaktionskosten, kein Kursverlust


def test_simulate_price_rise_and_overlay_of_own_position():
    later = row(400, 40, v_sol=45_000_000_000, v_tok=727_333_333_333_333, r_tok=447_433_333_333_333)  # ~15 SOL Zufluss danach
    rows = [row(100, 10), later]
    res = simulate(rows, t_entry=120.0, horizon_s=300.0, size_lamports=80_000_000, costs=Costs())
    assert res is not None and res["r_cons"] > 0.5
    assert res["exit_mc_sol"] > res["entry_mc_sol"]


def test_simulate_not_tradeable_without_state_or_after_completion():
    assert simulate([row(100, 10)], t_entry=50.0, horizon_s=60.0, size_lamports=80_000_000, costs=Costs()) is None
    assert simulate([row(100, 10, r_tok=0)], t_entry=130.0, horizon_s=60.0, size_lamports=80_000_000, costs=Costs()) is None


def test_simulate_graduation_before_exit_has_two_readings():
    rows = [row(100, 10), row(200, 20, v_sol=60_000_000_000, v_tok=545_500_000_000_000, r_tok=265_600_000_000_000), row(250, 25, v_sol=115_000_000_000, v_tok=279_900_000_000_000, r_tok=0)]
    costs = Costs()
    res = simulate(rows, t_entry=130.0, horizon_s=300.0, size_lamports=80_000_000, costs=costs)
    assert res is not None and res["graduated"]
    spent = 80_000_000 + 3 * costs.per_tx + costs.ata_rent
    assert abs(res["r_cons"] - (costs.ata_rent - spent) / spent) < 1e-12  # Position wertlos, nur die Einlage kommt zurück
    assert res["r_opt"] > 0.5  # Verkauf zum letzten Kurvenstand vor der Vollendung


def test_wilson_block_bootstrap_and_holm():
    assert wilson(0, 0) is None
    lo, hi = wilson(5, 10)
    assert abs(lo - 0.2366) < 0.001 and abs(hi - 0.7634) < 0.001
    pos = block_bootstrap([0.1, 0.2, 0.15, 0.3, 0.12, 0.25], [1, 1, 2, 2, 3, 3], n_boot=400)
    assert pos is not None and pos["lo"] > 0 and pos["p"] <= 0.01 and pos["blocks"] == 3
    sym = block_bootstrap([-0.1, 0.12, -0.2, 0.15, 0.1, -0.05], [1, 1, 2, 2, 3, 3], n_boot=400)
    assert sym is not None and sym["lo"] < 0 < sym["hi"] and sym["p"] > 0.2
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}


def _alert(mint: str, slot: int, alert_at: float, launched_at: float, tier: str = "GO") -> dict:
    return {"mint": mint, "tier": tier, "slot": slot, "alert_at": alert_at, "launch_received_at": launched_at, "rules_hash": "abc123def456", "word": tier, "flags": []}


def _token_rows(mint: str, t_launch: int, rise: bool) -> list[dict]:
    rows = []
    v_sol, v_tok, r_tok = V_SOL0, V_TOK0, R_TOK0
    for i in range(8):
        if rise and i >= 3:
            v_sol += 2_000_000_000
            v_tok -= 60_000_000_000_000
            r_tok -= 60_000_000_000_000
        rows.append(row(t_launch + 5 + i * 20, 1000 + i, v_sol=v_sol, v_tok=v_tok, r_tok=r_tok, t0=float(t_launch), mint=mint))
    return rows


def test_evaluate_matches_controls_and_marks_the_primary_combination():
    t = 1_800_000_000
    tape = {
        "A" * 44: _token_rows("A" * 44, t, rise=True),
        "B" * 44: _token_rows("B" * 44, t + 600, rise=False),
    }
    for i, name in enumerate("CDE"):
        rows = _token_rows(name * 44, t + 100 * i, rise=False)
        for r in rows:
            r["control"] = True
        tape[name * 44] = rows
    alerts = [
        _alert("A" * 44, slot=1003, alert_at=t + 70.5, launched_at=t),
        _alert("A" * 44, slot=1004, alert_at=t + 90.0, launched_at=t),  # zweiter GO desselben Tokens zählt nicht
        _alert("B" * 44, slot=1003, alert_at=t + 670.5, launched_at=t + 600),
        _alert("Z" * 44, slot=5, alert_at=t + 10.0, launched_at=t),  # kein Tape
    ]
    report = evaluate(alerts, tape, size_sol=0.08, latencies=(30.0,), horizons=(300.0,))
    assert report["alerts_evaluated"] == 2 and report["skipped"]["kein_tape"] == 1 and report["controls_available"] == 3
    s = report["summary"][("GO", 30.0, 300.0)]
    assert s["primary"] and s["n"] == 2 and s["tokens"] == 2 and s["n_paired"] == 2
    a = next(o for o in report["outcomes"] if o.mint == "A" * 44)
    b = next(o for o in report["outcomes"] if o.mint == "B" * 44)
    assert a.r_cons > 0 > b.r_cons and len(a.controls) == 3 and all(c < 0 for c in a.controls)
    assert abs(a.t_entry - (t + 65 + 30)) < 1e-9  # letzter Trade mit Slot <= 1003 liegt bei t+65
    assert s["mean_diff"] is not None and s["p_holm"] is None  # Primärzeile: roher p-Wert, keine Holm-Korrektur
    assert report["rules_hashes"] == ["abc123def456"]


def test_tape_report_end_to_end_with_files(tmp_path):
    t = 1_800_000_000
    records = tmp_path / "live.jsonl"
    tape = tmp_path / "tape.jsonl"
    lines = [
        json.dumps(_alert("A" * 44, slot=1003, alert_at=t + 70.5, launched_at=t)),
        json.dumps({"outcome_for": {"mint": "A" * 44}, "outcome": {"grew": True}}),
        json.dumps({"mint": "L" * 44, "tier": "GO", "recorded_at": t}),  # Record vor 0.3.1: kein Slot
    ]
    records.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = _token_rows("A" * 44, t, rise=True)
    for name in "CD":
        for r in _token_rows(name * 44, t + 50, rise=False):
            r["control"] = True
            rows.append(r)
    tape.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    text, report = tape_report(str(records), str(tape), latencies=(2.0, 30.0), horizons=(60.0, 300.0))
    assert "Records ohne Slot (vor 0.3.1): 1" in text and "*GO" in text and "Primär" in text
    assert len(report["summary"]) == 4 and sum(1 for s in report["summary"].values() if s["primary"]) == 1
    json.loads(replay.report_to_json(report))
    args = build_parser().parse_args(["tape", "report", str(records), str(tape), "--latenz", "30", "--horizont", "300", "--priority", "high", "--json", str(tmp_path / "out.json")])
    assert args.func is cmd_tape and cmd_tape(args) == 0 and (tmp_path / "out.json").exists()


def test_creator_fee_stats_are_a_lower_bound_from_the_tape():
    from holder_scorer.replay import creator_fee_stats

    rows_a = [row(100, 10, sol=1_000_000_000), row(160, 20, sol=2_000_000_000)]  # creator_fee = 0,30 % → 0.009 SOL
    rows_b = [row(100, 10, sol=50_000_000_000, mint="B" * 44)]  # 0.15 SOL
    stats = creator_fee_stats({"A" * 44: rows_a, "B" * 44: rows_b})
    assert stats["n"] == 2 and stats["median_sol"] == 0.0795 and stats["p90_sol"] == 0.009 and stats["max_sol"] == 0.15
    assert stats["share_over_0_1_sol"] == 0.5 and stats["median_volume_sol"] == 26.5 and stats["median_window_s"] == 30
    report = evaluate([], {"A" * 44: rows_a, "B" * 44: rows_b})
    assert report["creator_fees"] == stats and "Creator-Fee je beobachtetem Coin" in replay.format_report(report)
    assert creator_fee_stats({}) == {"n": 0} and "keine Gebührenfelder" in replay.format_report({**report, "creator_fees": creator_fee_stats({})})


def test_live_tape_sample_tapes_control_tokens_without_alert(tmp_path):
    engine, alerts = make_engine(stufe=1)
    engine.cfg.tape_path = str(tmp_path / "tape.jsonl")
    engine.cfg.tape_sample = 1.0
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    feed_buyers(engine, mint, creator, 2, T0 + 3, 1.0)
    engine.tick(T0 + 6)
    assert alerts == []
    rows = [json.loads(line) for line in (tmp_path / "tape.jsonl").read_text(encoding="utf-8").splitlines()]
    state = engine.tokens[b58encode(mint)]
    assert len(rows) == len(state.trades) and all(r["control"] and r["t0"] == T0 for r in rows)
    engine2, _ = make_engine(stufe=1)
    engine2.cfg.tape_path = str(tmp_path / "tape2.jsonl")
    engine2.cfg.tape_sample = 0.0
    mint2, creator2 = key(), key()
    engine2.on_launch(launch_msg(mint2, creator2), now=T0)
    feed_buyers(engine2, mint2, creator2, 2, T0 + 3, 1.0)
    assert not (tmp_path / "tape2.jsonl").exists()
    assert build_parser().parse_args(["live", "--tape", "t.jsonl", "--tape-sample", "0.1"]).tape_sample == 0.1
