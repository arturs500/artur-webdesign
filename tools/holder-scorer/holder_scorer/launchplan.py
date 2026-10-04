"""Launch-Rechner: was ein eigener pump.fun-Launch für Dev und Halter bedeutet, aus der Kurvenmathematik (OQ-029).

Kein Rat zu kaufen, kein Trading-Code. Der Rechner beantwortet mit den offiziellen Startparametern der Kurve
(pump-public-docs, direkt geprüft 2026-09-29: 30 SOL virtuelle Reserve, 1,073 Mrd. virtuelle Token, 793,1 Mio. reale
Token, Supply 1 Mrd., Gebühr 1,25 %) die Fragen, die ein fairer Launch vorab klären muss:

* Welchen Anteil der Supply kauft der Dev mit X SOL, und wo steht die MC danach für den ersten fremden Käufer?
* Wie viel Netto-Zufluss von anderen fehlt bis zur Graduation (reale Token-Reserve 0, ≈ 85 SOL)?
* Was ist die Dev-Position bei Graduation wert, was bringt der Verkauf eines kleinen Teils netto, und um wie viel
  drückt er den Kurs (Verkauf auf der Kurve kurz vor der Vollendung als Näherung; der PumpSwap-Pool danach ist
  anders tief)?
* Was wirft die Creator-Fee bis zur Graduation ab (0,30 % des Volumens; Annahme Volumen = Faktor × Zufluss)? Bei
  Holder-Rewards-Coins geht sie an die Halter, nicht an den Dev.
* Welche Sniper-Warnungen löst der Plan aus (DEV-GROSS ab 10 % Supply, siehe scoring.dev_big_hold)?

Nicht enthalten: Erstellungs-/Netzgebühren der Create-Transaktion (NICHT VERIFIZIERT), Preisimpact im PumpSwap-Pool,
Steuern. Alles Weitere zu Fairness und Recht in docs/fair_launch.md.
"""
from __future__ import annotations

from typing import Any, Iterable

from .paper import CURVE_FEE_BPS, buy_on_curve, sell_on_curve
from .pump import (
    INITIAL_REAL_TOKEN_RESERVES,
    INITIAL_VIRTUAL_SOL_RESERVES,
    INITIAL_VIRTUAL_TOKEN_RESERVES,
    LAMPORTS_PER_SOL,
    TOKEN_TOTAL_SUPPLY,
    BondingCurveState,
)

CREATOR_FEE_BPS = 30  # Anteil des Creators an der Kurvengebühr: 0,30 % (fees.png, direkt geprüft 2026-09-29; seit 09/2025 dynamisch)
DEV_BIG_HOLD = 0.10  # Sniper-Warnung DEV-GROSS ab diesem Supply-Anteil (scoring.ScoringConfig.dev_big_hold)
DEFAULT_DEV_BUYS = (0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0)
DEFAULT_SALE_SHARES = (0.25, 0.5)


def fresh_curve() -> BondingCurveState:
    return BondingCurveState(
        virtual_token_reserves=INITIAL_VIRTUAL_TOKEN_RESERVES,
        virtual_quote_reserves=INITIAL_VIRTUAL_SOL_RESERVES,
        real_token_reserves=INITIAL_REAL_TOKEN_RESERVES,
        real_quote_reserves=0,
        token_total_supply=TOKEN_TOTAL_SUPPLY,
        complete=False,
    )


def _mc_sol(curve: BondingCurveState) -> float:
    return curve.virtual_quote_reserves / curve.virtual_token_reserves * TOKEN_TOTAL_SUPPLY / LAMPORTS_PER_SOL


def plan(dev_buy_sol: float, sale_share: float, fee_bps: int = CURVE_FEE_BPS, volume_multiple: float = 2.0, holder_rewards: bool = False) -> dict[str, Any]:
    """Ein Szenario: Dev kauft ``dev_buy_sol`` beim Create, verkauft ``sale_share`` seiner Token bei Graduation."""
    c0 = fresh_curve()
    tokens, sol_cost, fee_in = buy_on_curve(c0, int(round(dev_buy_sol * LAMPORTS_PER_SOL)), fee_bps) if dev_buy_sol > 0 else (0, 0, 0)
    c1 = BondingCurveState(
        virtual_token_reserves=c0.virtual_token_reserves - tokens,
        virtual_quote_reserves=c0.virtual_quote_reserves + sol_cost,
        real_token_reserves=c0.real_token_reserves - tokens,
        real_quote_reserves=sol_cost,
        token_total_supply=TOKEN_TOTAL_SUPPLY,
        complete=False,
    )
    k = c1.virtual_quote_reserves * c1.virtual_token_reserves
    vt_grad = c1.virtual_token_reserves - c1.real_token_reserves  # reale Reserve 0: nur noch die virtuelle Grundmenge
    vs_grad = k // vt_grad
    inflow_needed = (vs_grad - c1.virtual_quote_reserves) / LAMPORTS_PER_SOL
    c_grad = BondingCurveState(
        virtual_token_reserves=vt_grad,
        virtual_quote_reserves=vs_grad,
        real_token_reserves=0,
        real_quote_reserves=vs_grad - INITIAL_VIRTUAL_SOL_RESERVES,
        token_total_supply=TOKEN_TOTAL_SUPPLY,
        complete=False,
    )
    price_grad = vs_grad / vt_grad
    dev_value_grad = tokens * price_grad / LAMPORTS_PER_SOL
    sell_tokens = int(tokens * sale_share)
    net_out, fee_out = sell_on_curve(c_grad, sell_tokens, fee_bps) if sell_tokens > 0 else (0, 0)
    gross_out = net_out + fee_out
    price_after = (vs_grad - gross_out) / (vt_grad + sell_tokens) if sell_tokens > 0 else price_grad
    volume = volume_multiple * (inflow_needed + sol_cost / LAMPORTS_PER_SOL)
    creator_fee = 0.0 if holder_rewards else volume * CREATOR_FEE_BPS / 10_000
    dev_share = tokens / TOKEN_TOTAL_SUPPLY
    flags: list[str] = []
    if dev_share >= DEV_BIG_HOLD:
        flags.append(f"DEV-GROSS ({dev_share * 100:.1f} % ≥ {DEV_BIG_HOLD * 100:.0f} %: kein GO beim Sniper)")
    if sale_share > 0.5:
        flags.append("Verkauf über die Hälfte: wirkt wie DEV-RAUS")
    if dev_buy_sol > 0 and price_grad / price_after - 1 > 0.15:
        flags.append("Kursimpact des Verkaufs über 15 %")
    return {
        "dev_buy_sol": dev_buy_sol,
        "dev_tokens": tokens,
        "dev_share": round(dev_share, 5),
        "fee_in_sol": fee_in / LAMPORTS_PER_SOL,
        "mc_after_dev_sol": round(_mc_sol(c1), 2),
        "mc_grad_sol": round(_mc_sol(c_grad), 2),
        "inflow_needed_sol": round(inflow_needed, 3),
        "multiple_first_buyer": round(_mc_sol(c_grad) / _mc_sol(c1), 2),
        "dev_value_grad_sol": round(dev_value_grad, 3),
        "dev_multiple": round(dev_value_grad / dev_buy_sol, 2) if dev_buy_sol > 0 else None,
        "sale_share": sale_share,
        "sale_net_sol": round(net_out / LAMPORTS_PER_SOL, 3),
        "sale_impact": round(1 - price_after / price_grad, 4) if sell_tokens > 0 else 0.0,
        "remaining_value_sol": round((tokens - sell_tokens) * price_after / LAMPORTS_PER_SOL, 3),
        "creator_fee_to_grad_sol": round(creator_fee, 3),
        "volume_assumed_sol": round(volume, 1),
        "holder_rewards": holder_rewards,
        "flags": flags,
    }


def table(dev_buys: Iterable[float] = DEFAULT_DEV_BUYS, sale_shares: Iterable[float] = DEFAULT_SALE_SHARES, **kwargs: Any) -> list[dict[str, Any]]:
    return [plan(d, s, **kwargs) for d in dev_buys for s in sale_shares]


def format_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "Launch-Rechner (Kurvenmathematik pump.fun, Startparameter direkt geprüft; Verkauf auf der Kurve kurz vor der Vollendung als Näherung; "
        "Create-/Netzgebühren nicht enthalten):",
        f"{'Dev-Kauf':>9}{'Supply':>8}{'MC danach':>11}{'Fremdzufluss':>13}{'x 1. Käufer':>12}{'Dev-Wert':>10}{'Verkauf':>8}{'netto':>8}{'Impact':>8}{'Rest':>8}{'Fee':>7}  Warnungen",
    ]
    for r in rows:
        lines.append(
            f"{r['dev_buy_sol']:>7.2f} S{r['dev_share'] * 100:>7.1f} %{r['mc_after_dev_sol']:>9.1f} S{r['inflow_needed_sol']:>11.1f} S{r['multiple_first_buyer']:>11.1f}x"
            f"{r['dev_value_grad_sol']:>8.1f} S{r['sale_share'] * 100:>6.0f} %{r['sale_net_sol']:>6.2f} S{r['sale_impact'] * 100:>6.1f} %{r['remaining_value_sol']:>6.1f} S"
            f"{r['creator_fee_to_grad_sol']:>5.2f} S  {', '.join(r['flags']) or '–'}"
        )
    lines.append(
        "Lesart: Fremdzufluss ist das Netto-SOL, das andere bis zur Graduation kaufen müssen; x 1. Käufer das Vielfache der MC von direkt nach dem "
        "Dev-Kauf bis zur Graduation; Fee die Creator-Fee bis dahin bei angenommenem Volumen = Faktor × Zufluss (0 bei Holder-Rewards). "
        "Nur rund 1 % der Launches graduieren (OQ-019): jede Zeile gilt unter der Bedingung, dass der Coin durchkommt."
    )
    return "\n".join(lines)
