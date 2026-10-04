"""Launch-Rechner (OQ-029): Kurvenmathematik eines eigenen Launches, Teilverkauf, Warnungen, CLI."""
from __future__ import annotations

from holder_scorer.cli import build_parser, cmd_launch
from holder_scorer.launchplan import format_table, plan, table


def test_plan_one_sol_dev_buy_matches_the_curve_math():
    p = plan(1.0, 0.25)
    assert 0.033 < p["dev_share"] < 0.035  # 1 SOL inkl. 1,25 % Gebühr → 0,9877 SOL auf die Kurve → rund 3,4 % der Supply
    assert abs(p["fee_in_sol"] - 0.01235) < 0.0005
    assert 83.9 < p["inflow_needed_sol"] < 84.1 and abs(p["mc_grad_sol"] - 410.9) < 0.5  # k ist invariant: Graduation bei 115 SOL virtuell
    assert 13.5 < p["multiple_first_buyer"] < 14.2 and 13.8 < p["dev_value_grad_sol"] < 14.4 and 13.8 < p["dev_multiple"] < 14.4
    assert 3.3 < p["sale_net_sol"] < 3.45 and 0.05 < p["sale_impact"] < 0.07 and 9.6 < p["remaining_value_sol"] < 10.2
    assert abs(p["creator_fee_to_grad_sol"] - 0.51) < 0.02 and p["flags"] == []
    assert plan(1.0, 0.25, holder_rewards=True)["creator_fee_to_grad_sol"] == 0.0


def test_plan_edge_cases_and_flags():
    zero = plan(0.0, 0.25)
    assert zero["dev_tokens"] == 0 and zero["dev_multiple"] is None and abs(zero["inflow_needed_sol"] - 85.0) < 0.01 and zero["sale_net_sol"] == 0.0 and zero["flags"] == []
    big = plan(5.0, 0.5)
    assert big["dev_share"] > 0.13 and any(f.startswith("DEV-GROSS") for f in big["flags"])
    assert any("Hälfte" in f for f in plan(1.0, 0.6)["flags"])
    heavy = plan(3.0, 0.5)
    assert heavy["sale_impact"] > 0.08 and heavy["sale_net_sol"] > heavy["dev_buy_sol"]  # die Hälfte bringt bei Graduation mehr als der Einsatz
    rows = table((0.5, 1.0), (0.25,))
    assert len(rows) == 2 and rows[0]["dev_share"] < rows[1]["dev_share"]
    text = format_table(rows)
    assert "Launch-Rechner" in text and "1 % der Launches" in text


def test_cli_launch_rechner(tmp_path):
    args = build_parser().parse_args(["launch", "rechner", "--dev-kauf", "0.5,1", "--verkauf", "0.25", "--volumen-faktor", "3", "--json", str(tmp_path / "l.json")])
    assert args.func is cmd_launch and cmd_launch(args) == 0 and (tmp_path / "l.json").exists()
