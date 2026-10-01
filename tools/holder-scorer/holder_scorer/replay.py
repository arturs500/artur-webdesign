"""Replay: Rendite-Label für Alarme aus Tape + Records, mit Kontrollgruppe (Edge Lab, Umbau P0).

Liest die Alarm-Records (``--record``, ab Version 0.3.1 mit Slot und Kurvenstand) und das Tape
(``--tape``: jeder gesehene Trade eines Tokens mit Alarm, plus eine Zufallsstichprobe anderer Token als
Kontrollgruppe über ``--tape-sample``) und rechnet je Alarm nach, was ein Follower verdient hätte:

* Einstieg L Sekunden nach dem Alarm (Standard 2, 10, 30, 60 s) zum Kurvenstand, der zu diesem Zeitpunkt
  galt (letzter Trade mit Blockzeit <= Alarm + L; Worst-Case-Ordnung: unsere Order landet zuletzt),
* Kauf auf der Konstantprodukt-Kurve mit der im Trade protokollierten Gebühr, eigener Preiseinfluss,
* Ausstieg nach H Sekunden (Standard 60, 300, 900 s) auf den realen Kurvenstand plus das eigene Delta
  ("Overlay": unsere Position liegt zusätzlich auf der Kurve; der Replay aller Folge-Trades ist Umbau P1),
* Kosten: Basisgebühr je Transaktion, Priority-Fee-Szenario, Token-Account-Einlage mit Rückholung,
* Graduation vor dem Ausstieg: optimistisch (Verkauf zum letzten Kurvenstand) und konservativ (Position 0).

Erfolgsmaß ist die Netto-Rendite in SOL, nicht das Holder-Wachstum. Die Kontrollgruppe sind zufällig
mitgeschriebene Token ohne Alarm, bewertet im gleichen Alter nach ihrem Launch (bis zu k je Alarm, Launch
innerhalb von 6 h). Edge = Differenz Alarm minus Kontrolle, nicht der absolute Mittelwert.

Statistik: Trefferquote mit Wilson-Intervall (beschreibend), Mittelwert mit Block-Bootstrap nach
Alarmstunde (Marktregime), zweiseitige Bootstrap-p-Werte, Holm-Korrektur über die sekundären
Kombinationen. Primär ist eine vorab festgelegte Kombination (GO, L = 30 s, H = 300 s); alles andere ist
sekundär und ändert keine Entscheidung. Paper-only: nichts hier handelt.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .paper import CURVE_FEE_BPS, buy_on_curve, sell_on_curve
from .pump import LAMPORTS_PER_SOL, TOKEN_TOTAL_SUPPLY, BondingCurveState

PRIMARY = ("GO", 30.0, 300.0)  # Tier, Latenz s, Horizont s – vorab festgelegt, siehe docs/sniper_review.md
DEFAULT_LATENCIES = (2.0, 10.0, 30.0, 60.0)
DEFAULT_HORIZONS = (60.0, 300.0, 900.0)
CONTROL_WINDOW_S = 6 * 3600.0


@dataclass(frozen=True)
class Costs:
    """Transaktionskosten je Seite, Lamports. Werte siehe PREREGISTRATION_EXP002.md Abschnitt 6.4."""

    base_fee: int = 5_000  # je Signatur (Solana-Doku, direkt geprüft)
    cu_limit: int = 120_000  # Default des offiziellen pump.fun-Skills
    cu_price_micro: int = 120_000  # "medium" aus der Helius-Priority-Fee-Doku (Beispielwert, keine Marktstatistik)
    ata_rent: int = 2_039_280  # Token-Account-Einlage – NICHT VERIFIZIERT, am Stichtag per RPC abfragen
    close_account: bool = True  # Einlage nach dem Verkauf zurückholen (eine weitere Transaktion)

    @property
    def priority_fee(self) -> int:
        return math.ceil(self.cu_price_micro * self.cu_limit / 1_000_000)

    @property
    def per_tx(self) -> int:
        return self.base_fee + self.priority_fee

    @classmethod
    def scenario(cls, name: str) -> "Costs":
        prices = {"low": 10_000, "medium": 120_000, "high": 500_000}
        if name not in prices:
            raise ValueError(f"unbekanntes Priority-Fee-Szenario {name!r} (low, medium, high)")
        return cls(cu_price_micro=prices[name])


@dataclass
class Outcome:
    mint: str
    tier: str
    latency_s: float
    horizon_s: float
    t_alert: float
    t_entry: float
    t_exit: float
    entry_mc_sol: float
    exit_mc_sol: float
    graduated: bool
    r_opt: float  # Netto-Rendite, Graduation optimistisch
    r_cons: float  # Netto-Rendite, Graduation konservativ (Position 0)
    trades_between: int
    block: int  # Stunde des Alarms (Block-Bootstrap)
    control: bool = False
    controls: list[float] = field(default_factory=list)  # r_cons der gematchten Kontroll-Token


# --- Laden --------------------------------------------------------------------------------------------


def load_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def load_alerts(path: str) -> tuple[list[dict[str, Any]], int]:
    """Alarm-Records ab 0.3.1 (mit Slot, Kurvenstand, alert_at). Returns (alerts, legacy_count)."""
    alerts, legacy = [], 0
    for rec in load_jsonl(path):
        if "outcome_for" in rec or "tier" not in rec:
            continue
        if rec.get("slot") is None or rec.get("alert_at") is None:
            legacy += 1
            continue
        alerts.append(rec)
    return alerts, legacy


def load_tape(path: str) -> dict[str, list[dict[str, Any]]]:
    """Tape-Zeilen je Mint, sortiert nach (Slot, Blockzeit, Empfangszeit)."""
    by_mint: dict[str, list[dict[str, Any]]] = {}
    for row in load_jsonl(path):
        mint = row.get("mint")
        if not mint or row.get("vT") is None or row.get("vS") is None:
            continue
        if not row.get("ts"):
            row["ts"] = int(row.get("seen_at") or 0)
        by_mint.setdefault(mint, []).append(row)
    for rows in by_mint.values():
        rows.sort(key=lambda r: (int(r.get("slot") or 0), int(r["ts"]), float(r.get("seen_at") or 0)))
    return by_mint


# --- Kurvenmathematik ---------------------------------------------------------------------------------


def curve_from_row(row: dict[str, Any], d_sol: int = 0, d_tok: int = 0) -> BondingCurveState:
    """Kurvenstand aus einer Tape-Zeile, optional mit dem eigenen Delta (Overlay) verschoben."""
    return BondingCurveState(
        virtual_token_reserves=int(row["vT"]) - d_tok,
        virtual_quote_reserves=int(row["vS"]) + d_sol,
        real_token_reserves=max(0, int(row.get("rT") or 0) - d_tok),
        real_quote_reserves=max(0, int(row.get("rS") or 0) + d_sol),
        token_total_supply=TOKEN_TOTAL_SUPPLY,
        complete=False,
        creator=None,
        quote_mint=None,
        is_mayhem_mode=False,
    )


def fee_bps_from_row(row: dict[str, Any]) -> int:
    """Protokollierte Gebühr des Trades in Basispunkten (Protokoll + Creator), sonst der Standardsatz."""
    sol = int(row.get("sol") or 0)
    fee = row.get("fee")
    if sol <= 0 or fee is None:
        return CURVE_FEE_BPS
    total = int(fee or 0) + int(row.get("creator_fee") or 0)
    bps = round(total * 10_000 / sol)
    return CURVE_FEE_BPS if bps <= 0 or bps > 1_000 else bps


def mc_sol(row: dict[str, Any]) -> float:
    vt = int(row["vT"])
    return 0.0 if vt <= 0 else int(row["vS"]) / vt * TOKEN_TOTAL_SUPPLY / LAMPORTS_PER_SOL


def state_at(rows: list[dict[str, Any]], t: float) -> dict[str, Any] | None:
    """Letzte Tape-Zeile mit Blockzeit <= t (Worst-Case: unsere Order landet nach allen Trades dieser Sekunde)."""
    last = None
    for row in rows:
        if int(row["ts"]) <= t:
            last = row
        else:
            break
    return last


def simulate(rows: list[dict[str, Any]], t_entry: float, horizon_s: float, size_lamports: int, costs: Costs) -> dict[str, Any] | None:
    """Ein Follower-Trade auf dem Tape: None, wenn kein handelbarer Kurvenstand existiert."""
    entry = state_at(rows, t_entry)
    if entry is None or int(entry.get("rT") or 0) <= 0:
        return None  # keine Daten oder Kurve schon komplett: nicht handelbar
    curve_in = curve_from_row(entry)
    tokens, sol_cost, _fee_in = buy_on_curve(curve_in, size_lamports, fee_bps_from_row(entry))
    if tokens <= 0:
        return None
    t_exit = t_entry + horizon_s
    exit_row = state_at(rows, t_exit) or entry
    graduated = int(exit_row.get("rT") or 0) <= 0
    if graduated:
        # optimistisch: Verkauf zum letzten Kurvenstand vor der Vollendung (immer >= Einstiegszeile)
        alive = [r for r in rows if int(r["ts"]) <= t_exit and int(r.get("rT") or 0) > 0]
        exit_row = alive[-1] if alive else entry
    curve_out = curve_from_row(exit_row, d_sol=sol_cost, d_tok=tokens)
    proceeds, _fee_out = sell_on_curve(curve_out, tokens, fee_bps_from_row(exit_row))
    n_tx = 3 if costs.close_account else 2
    tx_costs = n_tx * costs.per_tx
    rent = costs.ata_rent
    rent_back = costs.ata_rent if costs.close_account else 0
    spent = size_lamports + tx_costs + rent

    def ret(p: int) -> float:
        return (p + rent_back - spent) / spent

    between = sum(1 for r in rows if t_entry < int(r["ts"]) <= t_exit)
    return {
        "t_entry": t_entry,
        "t_exit": t_exit,
        "entry_mc_sol": mc_sol(entry),
        "exit_mc_sol": mc_sol(exit_row),
        "graduated": graduated,
        "r_opt": ret(proceeds),
        "r_cons": ret(0) if graduated else ret(proceeds),
        "trades_between": between,
    }


# --- Statistik ----------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def block_bootstrap(values: list[float], blocks: list[int], n_boot: int = 2000, seed: int = 20260929) -> dict[str, float] | None:
    """Perzentil-Intervall des Mittelwerts; Blöcke (z. B. Alarmstunden) werden mit Zurücklegen gezogen."""
    if len(values) < 2:
        return None
    groups: dict[int, list[float]] = {}
    for v, b in zip(values, blocks):
        groups.setdefault(b, []).append(v)
    keys = sorted(groups)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _k in keys:
            sample.extend(groups[rng.choice(keys)])
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(0.025 * (n_boot - 1))]
    hi = means[int(0.975 * (n_boot - 1))]
    below = sum(1 for m in means if m <= 0) / n_boot
    above = sum(1 for m in means if m >= 0) / n_boot
    p = max(1.0 / n_boot, 2 * min(below, above))
    return {"lo": lo, "hi": hi, "p": min(1.0, p), "blocks": len(keys)}


def holm(pvalues: dict[Any, float]) -> dict[Any, float]:
    """Holm-Bonferroni: korrigierte p-Werte für eine Familie von Tests."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    out: dict[Any, float] = {}
    running = 0.0
    for i, (key, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[key] = running
    return out


# --- Auswertung ---------------------------------------------------------------------------------------


def _launch_chain_time(rows: list[dict[str, Any]]) -> float:
    """Blockzeit des Launches, geschätzt aus der ersten Tape-Zeile und der Empfangszeit des Launches."""
    first = rows[0]
    t0 = first.get("t0")
    seen = first.get("seen_at")
    if t0 is not None and seen is not None:
        return int(first["ts"]) - (float(seen) - float(t0))
    return float(int(first["ts"]))


def evaluate(
    alerts: list[dict[str, Any]],
    tape: dict[str, list[dict[str, Any]]],
    size_sol: float = 0.08,
    latencies: Iterable[float] = DEFAULT_LATENCIES,
    horizons: Iterable[float] = DEFAULT_HORIZONS,
    costs: Costs | None = None,
    k_controls: int = 5,
    tiers: Iterable[str] | None = None,
) -> dict[str, Any]:
    costs = costs or Costs()
    size_lamports = int(round(size_sol * LAMPORTS_PER_SOL))
    alert_mints = {a["mint"] for a in alerts}
    controls = {m: rows for m, rows in tape.items() if m not in alert_mints and rows and rows[0].get("control")}
    control_launch = {m: (float(rows[0].get("t0") or rows[0].get("seen_at") or 0), _launch_chain_time(rows)) for m, rows in controls.items()}
    tiers_set = {t.upper() for t in tiers} if tiers else None

    outcomes: list[Outcome] = []
    skipped = {"kein_tape": 0, "kein_zustand_vor_alarm": 0, "nicht_handelbar": 0, "tier_filter": 0}
    first_per_token: dict[tuple[str, str], str] = {}
    for rec in alerts:
        tier = str(rec.get("tier", "")).upper()
        if tiers_set and tier not in tiers_set:
            skipped["tier_filter"] += 1
            continue
        mint = rec["mint"]
        rows = tape.get(mint)
        if not rows:
            skipped["kein_tape"] += 1
            continue
        key = (mint, tier)
        if key in first_per_token:
            continue  # ein Alarm je Stufe und Token (der erste zählt)
        first_per_token[key] = rec.get("rules_hash", "")
        before = [r for r in rows if int(r.get("slot") or 0) <= int(rec["slot"])]
        if not before:
            skipped["kein_zustand_vor_alarm"] += 1
            continue
        t_alert = float(int(before[-1]["ts"]))
        age = float(rec["alert_at"]) - float(rec.get("launch_received_at") or rec["alert_at"])
        block = int(float(rec["alert_at"]) // 3600)
        # Kontroll-Token: Launch innerhalb von 6 h, im gleichen Alter noch handelbar
        candidates = []
        for cm, (t0_wall, t0_chain) in control_launch.items():
            gap = abs(t0_wall - float(rec.get("launch_received_at") or 0))
            if gap <= CONTROL_WINDOW_S:
                candidates.append((gap, cm, t0_chain))
        candidates.sort()
        for lat in latencies:
            for hor in horizons:
                res = simulate(rows, t_alert + lat, hor, size_lamports, costs)
                if res is None:
                    skipped["nicht_handelbar"] += 1
                    continue
                ctrl_returns: list[float] = []
                for _gap, cm, t0_chain in candidates:
                    cres = simulate(controls[cm], t0_chain + age + lat, hor, size_lamports, costs)
                    if cres is not None:
                        ctrl_returns.append(cres["r_cons"])
                    if len(ctrl_returns) >= k_controls:
                        break
                outcomes.append(
                    Outcome(
                        mint=mint,
                        tier=tier,
                        latency_s=lat,
                        horizon_s=hor,
                        t_alert=t_alert,
                        block=block,
                        controls=ctrl_returns,
                        **res,
                    )
                )

    combos: dict[tuple[str, float, float], dict[str, Any]] = {}
    for o in outcomes:
        combos.setdefault((o.tier, o.latency_s, o.horizon_s), {"items": []})["items"].append(o)
    summary: dict[str, Any] = {}
    pvals: dict[tuple[str, float, float], float] = {}
    for key, data in combos.items():
        items: list[Outcome] = data["items"]
        r_cons = [o.r_cons for o in items]
        r_opt = [o.r_opt for o in items]
        blocks = [o.block for o in items]
        hits = sum(1 for r in r_cons if r > 0)
        paired = [(o.r_cons - sum(o.controls) / len(o.controls), o.block) for o in items if len(o.controls) >= 2]
        boot = block_bootstrap(r_cons, blocks)
        boot_diff = block_bootstrap([d for d, _ in paired], [b for _, b in paired]) if len(paired) >= 2 else None
        if boot is not None:
            pvals[key] = boot["p"]
        summary[key] = {
            "n": len(items),
            "tokens": len({o.mint for o in items}),
            "hit_rate": hits / len(items),
            "wilson": wilson(hits, len(items)),
            "mean_cons": sum(r_cons) / len(items),
            "mean_opt": sum(r_opt) / len(items),
            "median_cons": statistics.median(r_cons),
            "boot": boot,
            "graduated_share": sum(1 for o in items if o.graduated) / len(items),
            "n_paired": len(paired),
            "mean_diff": (sum(d for d, _ in paired) / len(paired)) if paired else None,
            "boot_diff": boot_diff,
            "trades_between_median": statistics.median(o.trades_between for o in items),
        }
    secondary = {k: p for k, p in pvals.items() if k != PRIMARY}
    adjusted = holm(secondary) if secondary else {}
    for key, s in summary.items():
        s["p_raw"] = pvals.get(key)
        s["p_holm"] = None if key == PRIMARY else adjusted.get(key)
        s["primary"] = key == PRIMARY

    params = {
        "size_sol": size_sol,
        "latencies": list(latencies),
        "horizons": list(horizons),
        "costs": asdict(costs),
        "k_controls": k_controls,
        "primary": list(PRIMARY),
        "impact_model": "overlay",
    }
    params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {
        "params": params,
        "params_hash": params_hash,
        "alerts_total": len(alerts),
        "alerts_evaluated": len(first_per_token),
        "controls_available": len(controls),
        "rules_hashes": sorted({h for h in first_per_token.values() if h}),
        "skipped": skipped,
        "summary": summary,
        "outcomes": outcomes,
    }


def format_report(report: dict[str, Any], legacy: int = 0) -> str:
    def pct(x: float | None) -> str:
        return "–" if x is None else f"{x * 100:+.1f} %"

    def ci(b: dict[str, float] | None) -> str:
        return "–" if b is None else f"[{b['lo'] * 100:+.1f} %, {b['hi'] * 100:+.1f} %]"

    p = report["params"]
    lines = [
        f"Replay (Parameter-Hash {report['params_hash']}): Einsatz {p['size_sol']} SOL, Kosten je Tx {Costs(**p['costs']).per_tx} Lamports "
        f"(Priority {Costs(**p['costs']).priority_fee}), Token-Account-Einlage {p['costs']['ata_rent']} Lamports (NICHT VERIFIZIERT), Impact-Modell {p['impact_model']}.",
        f"Alarme: {report['alerts_total']} Records, {report['alerts_evaluated']} bewertet (ein Alarm je Stufe und Token); "
        f"übersprungen: {', '.join(f'{k} {v}' for k, v in report['skipped'].items())}; Records ohne Slot (vor 0.3.1): {legacy}.",
        f"Kontroll-Token im Tape: {report['controls_available']} (Launch innerhalb von 6 h, gleiches Alter, bis zu {p['k_controls']} je Alarm). "
        f"Regel-Hashes der Alarme: {', '.join(report['rules_hashes']) or '–'}.",
        "",
        "Primär: GO · Einstieg +30 s · Ausstieg +300 s (vorab festgelegt). Rendite = Netto in SOL nach Gebühren, Priority-Fees, Einlage; "
        "Graduation vor Ausstieg konservativ = Position 0 (optimistischer Wert daneben). p-Werte der sekundären Zeilen Holm-korrigiert.",
        "",
        f"{'Tier':<9}{'L s':>5}{'H s':>6}{'n':>5}{'Treffer':>9}{'Wilson 95 %':>20}{'Ø netto':>10}{'Bootstrap 95 %':>22}{'Median':>9}{'Ø opt.':>9}{'Grad.':>7}{'n Paar':>7}{'Ø Diff':>9}{'Diff 95 %':>22}{'p':>8}",
    ]
    for key in sorted(report["summary"], key=lambda k: (k != PRIMARY, k[0], k[1], k[2])):
        s = report["summary"][key]
        tier, lat, hor = key
        w = s["wilson"]
        wil = "–" if w is None else f"[{w[0] * 100:.0f} %, {w[1] * 100:.0f} %]"
        pval = s["p_raw"] if s["primary"] else s["p_holm"]
        mark = "*" if s["primary"] else " "
        lines.append(
            f"{mark}{tier:<8}{lat:>5.0f}{hor:>6.0f}{s['n']:>5}{s['hit_rate'] * 100:>8.0f} %{wil:>20}{pct(s['mean_cons']):>10}{ci(s['boot']):>22}"
            f"{pct(s['median_cons']):>9}{pct(s['mean_opt']):>9}{s['graduated_share'] * 100:>6.0f} %{s['n_paired']:>7}{pct(s['mean_diff']):>9}{ci(s['boot_diff']):>22}"
            f"{('–' if pval is None else f'{pval:.3f}'):>8}"
        )
    if not report["summary"]:
        lines.append("(keine auswertbaren Alarme – Records mit Slot ab Version 0.3.1 und ein Tape mit --tape nötig)")
    lines += [
        "",
        "Lesart: Ein Edge liegt erst vor, wenn in der Primärzeile sowohl das Bootstrap-Intervall des Mittelwerts als auch das der Differenz zur "
        "Kontrollgruppe vollständig über 0 liegen – bei mindestens 200 Alarmen aus mindestens 30 Alarmstunden. Sekundäre Zeilen sind Hinweise, "
        "keine Entscheidung. Vor einem Live-Einsatz ist eine Vorregistrierung (EXP003) Pflicht.",
    ]
    return "\n".join(lines)


def tape_report(records_path: str, tape_path: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
    alerts, legacy = load_alerts(records_path)
    tape = load_tape(tape_path)
    report = evaluate(alerts, tape, **kwargs)
    return format_report(report, legacy), report


def report_to_json(report: dict[str, Any]) -> str:
    out = {k: v for k, v in report.items() if k != "outcomes"}
    out["summary"] = {"|".join(str(x) for x in k): v for k, v in report["summary"].items()}
    out["outcomes"] = [asdict(o) for o in report["outcomes"]]
    return json.dumps(out, ensure_ascii=False, indent=2, default=str)
