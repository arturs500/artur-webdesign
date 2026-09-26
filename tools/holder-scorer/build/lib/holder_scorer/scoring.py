"""Score a token's chance of gaining holders from its features.

The model is a transparent point system: seven factors with fixed maximum
points plus hard-fail rules that override everything. All thresholds live in
``ScoringConfig`` so they can be tuned, and ``calibrate.py`` measures how well
each factor actually predicts holder growth on the tokens you recorded.

The default weights are informed by public research on pump.fun launches
(deployer history and bundling are the strongest known signals, holder
momentum is the best short-term predictor of further momentum) but they are
heuristics until you calibrate them on your own data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .features import Features

LABEL_YES = "JA"
LABEL_UNCLEAR = "UNKLAR"
LABEL_NO = "NEIN"
LABEL_TOO_EARLY = "ZU_FRUEH"
LABEL_GRADUATED = "GRADUIERT"
LABEL_NO_DATA = "KEINE_DATEN"


@dataclass
class ScoringConfig:
    min_age_s: float = 45.0
    yes_threshold: float = 65.0
    no_threshold: float = 45.0
    # hard-fail rules
    dev_dump_share: float = 0.9
    dev_dump_min_buy: float = 0.02
    max_top10_share: float = 0.60
    max_largest_holder: float = 0.30
    max_creation_window_share: float = 0.35
    serial_creator_min_tokens: int = 5
    serial_creator_dead_share: float = 0.8
    stall_age_s: float = 180.0
    stall_gap_s: float = 120.0
    max_wash_share: float = 0.40
    # factor weights (maximum points, sum = 100)
    w_momentum: float = 25.0
    w_pressure: float = 15.0
    w_creator: float = 20.0
    w_distribution: float = 20.0
    w_dev: float = 10.0
    w_organic: float = 5.0
    w_socials: float = 5.0


@dataclass
class FactorResult:
    name: str
    points: float
    max_points: float
    value: str
    comment: str = ""


@dataclass
class Verdict:
    mint: str
    label: str
    score: float
    hard_fails: list[str]
    factors: list[FactorResult]
    features: Features
    notes: list[str] = field(default_factory=list)

    @property
    def buy_signal(self) -> bool:
        return self.label == LABEL_YES

    def to_dict(self) -> dict:
        return {
            "mint": self.mint,
            "label": self.label,
            "score": round(self.score, 1),
            "hard_fails": list(self.hard_fails),
            "factors": [asdict(f) for f in self.factors],
            "features": self.features.to_dict(),
            "notes": list(self.notes),
        }


def _interp(x: float, points: list[tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _pct(x: float | None) -> str:
    return "?" if x is None else f"{x * 100:.1f} %"


def hard_fail_reasons(f: Features, cfg: ScoringConfig) -> list[str]:
    reasons: list[str] = []
    if f.dev_buy_share is not None and f.dev_sold_share is not None:
        if f.dev_buy_share >= cfg.dev_dump_min_buy and f.dev_sold_share >= cfg.dev_dump_share:
            reasons.append(f"Dev hat {_pct(f.dev_sold_share)} seiner Token verkauft (Dev-Dump)")
    if f.top10_share is not None and f.top10_share >= cfg.max_top10_share:
        reasons.append(f"Top-10-Wallets halten {_pct(f.top10_share)} des Supplys")
    if f.largest_holder_share is not None and f.largest_holder_share >= cfg.max_largest_holder:
        reasons.append(f"größter Holder hält {_pct(f.largest_holder_share)} des Supplys")
    if f.creation_window_share is not None and f.creation_window_share >= cfg.max_creation_window_share:
        reasons.append(f"{_pct(f.creation_window_share)} des Supplys im Erstellungs-Block gekauft (Bundle)")
    if (
        f.creator_prior_tokens is not None
        and f.creator_prior_tokens >= cfg.serial_creator_min_tokens
        and (f.creator_graduated or 0) == 0
        and (f.creator_dead or 0) / max(f.creator_prior_tokens, 1) >= cfg.serial_creator_dead_share
    ):
        reasons.append(
            f"Creator hat {f.creator_prior_tokens} frühere Token, {f.creator_dead} davon tot, 0 graduiert (Serien-Deployer)"
        )
    if (
        f.age_s is not None
        and f.seconds_since_last_trade is not None
        and f.age_s >= cfg.stall_age_s
        and f.seconds_since_last_trade >= cfg.stall_gap_s
    ):
        reasons.append(f"kein Trade seit {f.seconds_since_last_trade:.0f} s (Token ist eingeschlafen)")
    if f.wash_share is not None and f.wash_share >= cfg.max_wash_share and f.unique_traders >= 5:
        reasons.append(f"{_pct(f.wash_share)} der Wallets handeln hin und her (Wash-Trading)")
    return reasons


def _momentum(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_momentum
    comment = ""
    if f.holder_growth_60s is not None:
        g = f.holder_growth_60s
        pts = _interp(g, [(-0.2, -10.0), (0.0, 0.0), (0.15, mx * 0.5), (0.4, mx)])
        value = f"Holder {f.holders_60s_ago} → {f.holders_now} in 60 s ({g * 100:+.0f} %)"
    else:
        base = max(f.holders_now or 0, 10)
        rate = f.new_buyers_60s / base
        pts = _interp(rate, [(0.0, 0.0), (0.15, mx * 0.5), (0.4, mx)])
        value = f"{f.new_buyers_60s} neue Käufer in 60 s bei {f.holders_now if f.holders_now is not None else '?'} Holdern"
        comment = "Holder-Verlauf unbekannt, Näherung über neue Käufer"
    if (f.holders_now or 0) < 10 and (f.age_s or 0) > 120:
        pts = min(pts, mx * 0.2)
        comment = "zu wenige Holder für das Alter des Tokens"
    return FactorResult("Holder-Momentum", pts, mx, value, comment)


def _pressure(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_pressure
    total = f.buys_120s + f.sells_120s
    if total == 0:
        return FactorResult("Kaufdruck", 0.0, mx, "keine Trades in 120 s", "")
    if f.sells_120s == 0:
        ratio = 3.0 if f.buys_120s >= 3 else 1.5
    else:
        ratio = f.buys_120s / f.sells_120s
    pts = _interp(ratio, [(0.7, 0.0), (1.0, mx * 0.4), (1.5, mx * 0.67), (2.5, mx)])
    comment = ""
    if f.net_flow_120s_sol is not None and f.net_flow_120s_sol < 0:
        pts = max(0.0, pts - 3.0)
        comment = f"Netto-Abfluss {f.net_flow_120s_sol:.2f} SOL in 120 s"
    value = f"{f.buys_120s} Käufe / {f.sells_120s} Verkäufe in 120 s"
    return FactorResult("Kaufdruck", pts, mx, value, comment)


def _creator(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_creator
    if f.creator_prior_tokens is None:
        return FactorResult("Creator-Historie", mx * 0.4, mx, "unbekannt", "keine Creator-Daten verfügbar")
    prior = f.creator_prior_tokens
    if prior == 0:
        pts = mx * 0.6
        value = "erster Token dieses Creators"
    else:
        grad_rate = (f.creator_graduated or 0) / prior
        dead_rate = (f.creator_dead or 0) / prior
        pts = mx * max(0.0, min(1.0, 0.3 + grad_rate * 2.5 - dead_rate * 0.6))
        value = f"{prior} frühere Token, {f.creator_graduated} graduiert, {f.creator_dead} tot"
    comment = ""
    if f.creator_is_fresh:
        pts -= 4.0
        comment = "Creator-Wallet ist frisch (jünger als 1 Tag, kaum Transaktionen)"
    return FactorResult("Creator-Historie", max(0.0, pts), mx, value, comment)


def _distribution(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_distribution
    if f.creation_window_share is None and f.top10_share is None:
        return FactorResult("Verteilung", mx * 0.5, mx, "unbekannt", "weder Bundle- noch Holder-Daten")
    pts = mx
    parts: list[str] = []
    if f.creation_window_share is not None:
        pts -= min(mx, 60.0 * f.creation_window_share)
        parts.append(f"Bundle-Anteil {_pct(f.creation_window_share)} ({f.creation_slot_buyers} Wallets)")
    if f.top10_share is not None:
        if f.top10_share > 0.15:
            pts -= (f.top10_share - 0.15) * 40.0
        parts.append(f"Top-10 {_pct(f.top10_share)}")
    comments: list[str] = []
    if f.early_fresh_wallets > 1:
        pts -= 3.0 * (f.early_fresh_wallets - 1)
        comments.append(f"{f.early_fresh_wallets} von {f.early_wallets_checked} frühen Wallets sind frisch")
    if f.early_funded_by_creator:
        pts -= 6.0 * f.early_funded_by_creator
        comments.append(f"{f.early_funded_by_creator} frühe Wallets vom Creator finanziert")
    elif f.early_shared_funder_max >= 3:
        pts -= 6.0
        comments.append(f"{f.early_shared_funder_max} frühe Wallets mit derselben Finanzierungsquelle")
    return FactorResult("Verteilung", max(0.0, min(mx, pts)), mx, ", ".join(parts), "; ".join(comments))


def _dev(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_dev
    if f.dev_buy_share is None or f.dev_sold_share is None:
        return FactorResult("Dev-Verhalten", mx * 0.5, mx, "unbekannt", "")
    buy, sold = f.dev_buy_share, f.dev_sold_share
    if buy == 0:
        pts, value = mx * 0.8, "Dev hat nicht gekauft"
    elif buy <= 0.05:
        pts, value = mx, f"Dev-Kauf {_pct(buy)}"
    elif buy <= 0.10:
        pts, value = mx * 0.6, f"Dev-Kauf {_pct(buy)}"
    else:
        pts, value = mx * 0.2, f"Dev-Kauf {_pct(buy)} (groß)"
    comment = ""
    if buy > 0 and sold > 0:
        pts = max(0.0, pts - 5.0) if sold < cfg.dev_dump_share else 0.0
        comment = f"Dev hat {_pct(sold)} seiner Token verkauft"
    elif buy > 0:
        comment = "Dev hält noch alles"
    return FactorResult("Dev-Verhalten", pts, mx, value, comment)


def _organic(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_organic
    if f.small_buy_share is None:
        return FactorResult("Organische Käufe", mx * 0.4, mx, "unbekannt", "")
    pts = _interp(f.small_buy_share, [(0.2, mx * 0.2), (0.4, mx * 0.6), (0.6, mx)])
    med = f"{f.median_buy_sol:.3f} SOL" if f.median_buy_sol is not None else "?"
    value = f"{_pct(f.small_buy_share)} der Käufe unter 0,1 SOL, Median {med}"
    return FactorResult("Organische Käufe", pts, mx, value, "")


def _socials(f: Features, cfg: ScoringConfig) -> FactorResult:
    mx = cfg.w_socials
    if f.socials_count is None:
        return FactorResult("Socials", mx * 0.4, mx, "Metadaten nicht abrufbar", "")
    pts = {0: 0.0, 1: mx * 0.6}.get(f.socials_count, mx)
    value = f"{f.socials_count} Social-Links" + ("" if f.has_image else ", kein Bild")
    return FactorResult("Socials", pts, mx, value, "")


def score_features(f: Features, cfg: ScoringConfig | None = None) -> Verdict:
    cfg = cfg or ScoringConfig()
    factors = [
        _momentum(f, cfg),
        _pressure(f, cfg),
        _creator(f, cfg),
        _distribution(f, cfg),
        _dev(f, cfg),
        _organic(f, cfg),
        _socials(f, cfg),
    ]
    total = max(0.0, min(100.0, sum(x.points for x in factors)))
    fails = hard_fail_reasons(f, cfg)
    notes: list[str] = []
    if f.complete:
        label = LABEL_GRADUATED
        notes.append("Bonding Curve ist voll, Token handelt bereits auf PumpSwap")
    elif f.n_trades == 0:
        label = LABEL_NO_DATA
        notes.append("keine Trades gefunden")
    elif fails:
        label = LABEL_NO
    elif f.age_s is not None and f.age_s < cfg.min_age_s:
        label = LABEL_TOO_EARLY
        notes.append(f"Token ist erst {f.age_s:.0f} s alt, Momentum noch nicht messbar")
    elif total >= cfg.yes_threshold:
        label = LABEL_YES
    elif total < cfg.no_threshold:
        label = LABEL_NO
    else:
        label = LABEL_UNCLEAR
    if f.partial_history:
        notes.append("Trade-Historie unvollständig, Bundle- und Dev-Werte teilweise unbekannt")
    return Verdict(mint=f.mint, label=label, score=total, hard_fails=fails, factors=factors, features=f, notes=notes)


def format_verdict(v: Verdict) -> str:
    f = v.features
    lines = [f"Token {v.mint}"]
    age = f"{f.age_s:.0f} s" if f.age_s is not None else "?"
    lines.append(
        f"Alter {age} | Trades {f.n_trades} | Holder {f.holders_now if f.holders_now is not None else '?'} ({f.holders_source})"
        f" | Kurve {_pct(f.progress)} | Quelle SOL: {'ja' if f.quote_is_sol else 'nein'}"
    )
    lines.append("")
    for x in v.factors:
        lines.append(f"  {x.name:<18} {x.points:5.1f} / {x.max_points:<4.0f} {x.value}" + (f"  [{x.comment}]" if x.comment else ""))
    lines.append("")
    lines.append(f"Score {v.score:.0f} / 100  →  {v.label}")
    for r in v.hard_fails:
        lines.append(f"  ✗ {r}")
    for n in v.notes:
        lines.append(f"  · {n}")
    return "\n".join(lines)
