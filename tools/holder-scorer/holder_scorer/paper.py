"""Papier-Trading: alle Strategien handeln jeden Call gleichzeitig, ohne echtes Geld.

The live engine scores a token after every trade (at most once a second) and raises the
alerts BLICK, GO and RUG. The paper trader hooks into both:

* every strategy decides at every evaluation whether it enters: trigger BLICK, GO or
  FRÜH (before any alert, with its own filters such as narrative score, dev still
  holding, no bundle);
* buys and sells are priced on the bonding curve exactly like real ones (constant
  product on the virtual reserves, 1.25 % pump.fun fee, the position's own price
  impact), using the curve state ``latency_s`` after the decision, because a real
  transaction lands a couple of seconds after the signal;
* every second the open positions are checked against the current curve: take profit,
  stop loss, trailing stop, partial sale, time limit, RUG/TOT verdict, dev sale,
  graduation;
* everything is appended to a JSONL file: every buy with its reason and the numbers it
  was based on, every sale with reason and result, and per token the price path (one
  point every 5 s with the high and low in between), so ``paper report`` can also try
  rules that never ran.

Nothing here sends a transaction.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from .narrative import narrative_score
from .pump import (
    LAMPORTS_PER_SOL,
    TOKEN_DECIMALS,
    TOKEN_TOTAL_SUPPLY,
    BondingCurveState,
    parse_transaction,
)
from .quick import GO_BLOCKING_FLAGS, QuickReport

CURVE_FEE_BPS = 125  # pump.fun bonding curve: 0.95 % protocol + 0.30 % creator (fee program, September 2026)
RAW_PER_TOKEN = 10**TOKEN_DECIMALS
SUPPLY_TOKENS = TOKEN_TOTAL_SUPPLY / RAW_PER_TOKEN


# --- curve math -----------------------------------------------------------------------------------


def curve_price(curve: BondingCurveState) -> float:
    """Marginal price in SOL per token."""
    if curve.virtual_token_reserves <= 0:
        return 0.0
    return (curve.virtual_quote_reserves / LAMPORTS_PER_SOL) / (curve.virtual_token_reserves / RAW_PER_TOKEN)


def buy_on_curve(curve: BondingCurveState, budget_lamports: int, fee_bps: int = CURVE_FEE_BPS) -> tuple[int, int, int]:
    """Spend ``budget_lamports`` (fee included) on the curve. Returns (tokens raw, sol paid to the curve, fee)."""
    if budget_lamports <= 0 or curve.virtual_token_reserves <= 0:
        return 0, 0, 0
    sol_cost = budget_lamports * 10_000 // (10_000 + fee_bps)
    tokens = curve.virtual_token_reserves * sol_cost // (curve.virtual_quote_reserves + sol_cost)
    tokens = max(0, min(tokens, curve.real_token_reserves))
    if tokens <= 0:
        return 0, 0, 0
    return tokens, sol_cost, budget_lamports - sol_cost


def sell_on_curve(curve: BondingCurveState, tokens: int, fee_bps: int = CURVE_FEE_BPS) -> tuple[int, int]:
    """Sell ``tokens`` (raw) into the curve. Returns (net sol received, fee)."""
    if tokens <= 0 or curve.virtual_token_reserves <= 0:
        return 0, 0
    sol_out = curve.virtual_quote_reserves * tokens // (curve.virtual_token_reserves + tokens)
    sol_out = min(sol_out, curve.real_quote_reserves) if curve.real_quote_reserves > 0 else sol_out
    fee = sol_out * fee_bps // 10_000
    return sol_out - fee, fee


# --- strategies -----------------------------------------------------------------------------------


@dataclass
class Strategy:
    name: str
    entry: str  # BLICK | GO | FRÜH (FRÜH = at any evaluation, before any alert)
    tp: float | None = 3.0  # take profit at this multiple of the effective entry price
    sl: float | None = 0.4  # stop loss when the price falls this fraction below the entry
    trail: float | None = None  # trailing stop: exit this fraction below the peak once armed
    trail_arm: float = 1.5  # the trailing stop arms once the price reaches this multiple
    partial_tp: float | None = None  # sell ``partial_share`` at this multiple, keep the rest
    partial_share: float = 0.5
    max_hold_s: float = 600.0
    exit_on_rug: bool = True  # sell on the engine's RUG/TOT verdict
    exit_on_dev_sell: bool = False  # sell as soon as the dev sells a part (DEV-RAUS)
    dev_must_hold: bool = False  # enter only while the dev has sold nothing
    max_bundle: float | None = None  # enter only when the creation-block share is at most this
    min_narrative: int | None = None  # enter only with at least this narrative score
    min_outside_buyers: int | None = None
    no_warnings: bool = False  # enter only without any warning flag (NOSOC, MINDEST and LÜCKE allowed)
    description: str = ""


STRATEGIES: list[Strategy] = [
    Strategy("GO-3x", "GO", tp=3.0, sl=0.4, description="Kauf beim GO, Ziel 3x, Stop −40 %, 10 min"),
    Strategy("GO-2x", "GO", tp=2.0, sl=0.35, description="Kauf beim GO, Ziel 2x, Stop −35 %, 10 min"),
    Strategy("GO-schnell", "GO", tp=1.5, sl=0.25, max_hold_s=180.0, description="Kauf beim GO, Ziel 1,5x, Stop −25 %, 3 min"),
    Strategy("GO-trail", "GO", tp=None, sl=0.4, trail=0.3, trail_arm=1.5, max_hold_s=900.0, description="Kauf beim GO, ab 1,5x Trailing-Stop 30 %, 15 min"),
    Strategy("GO-halb", "GO", tp=None, sl=0.4, partial_tp=2.0, partial_share=0.5, trail=0.35, trail_arm=2.0, max_hold_s=900.0, description="Kauf beim GO, Hälfte bei 2x, Rest mit Trailing-Stop 35 %"),
    Strategy("GO-bis-RUG", "GO", tp=None, sl=None, max_hold_s=900.0, exit_on_dev_sell=True, description="Kauf beim GO, Verkauf nur bei RUG/TOT, Dev-Verkauf oder nach 15 min"),
    Strategy("DEV-HÄLT", "GO", tp=3.0, sl=0.4, dev_must_hold=True, exit_on_dev_sell=True, description="GO nur wenn der Dev noch nichts verkauft hat, raus sobald er verkauft"),
    Strategy("NARRATIV-GO", "GO", tp=3.0, sl=0.4, min_narrative=60, description="GO nur mit Narrativ-Score 60+ (Socials, Beschreibung, Trend, keine Kopie)"),
    Strategy("BLICK-3x", "BLICK", tp=3.0, sl=0.5, description="Kauf schon beim BLICK, Ziel 3x, Stop −50 %"),
    Strategy("BLICK-trail", "BLICK", tp=None, sl=0.5, trail=0.35, trail_arm=1.5, max_hold_s=900.0, description="Kauf beim BLICK, ab 1,5x Trailing-Stop 35 %"),
    Strategy("NARRATIV-früh", "FRÜH", tp=3.0, sl=0.5, min_narrative=60, dev_must_hold=True, max_bundle=0.05, min_outside_buyers=2, description="vor jedem Alarm: Narrativ 60+, Dev hält, Bundle ≤ 5 %, ab 2 echten Käufern"),
    Strategy("SAUBER-früh", "FRÜH", tp=2.0, sl=0.4, max_hold_s=300.0, dev_must_hold=True, max_bundle=0.02, min_outside_buyers=3, no_warnings=True, description="vor jedem Alarm: keine Warnung, Dev hält, kein Bundle, ab 3 echten Käufern, Ziel 2x, 5 min"),
]


def strategies_by_name(names: Iterable[str] | None) -> list[Strategy]:
    if not names:
        return list(STRATEGIES)
    wanted = {n.strip().lower() for n in names if n.strip()}
    if "alle" in wanted:
        return list(STRATEGIES)
    out = [s for s in STRATEGIES if s.name.lower() in wanted]
    unknown = wanted - {s.name.lower() for s in out}
    if unknown:
        raise ValueError("unbekannte Strategie(n): " + ", ".join(sorted(unknown)) + " (bekannt: " + ", ".join(s.name for s in STRATEGIES) + ")")
    return out


# --- state ----------------------------------------------------------------------------------------


@dataclass
class Order:
    strategy: str
    mint: str
    placed_at: float
    execute_at: float
    reason: str
    context: dict[str, Any]


@dataclass
class Position:
    strategy: str
    mint: str
    opened_at: float
    entry_price: float  # effective SOL per token paid, fee and impact included
    tokens: int  # raw units still held
    tokens_initial: int
    sol_in: int  # lamports spent, fee included
    context: dict[str, Any]
    sol_out: int = 0  # lamports received so far, net of fees
    fees: int = 0
    peak: float = 0.0
    trough: float = float("inf")
    partial_done: bool = False
    trail_armed: bool = False
    last_price: float = 0.0
    pending_exit: tuple[str, float, float] | None = None  # (reason, share, execute_at)

    @property
    def multiple(self) -> float:
        return self.last_price / self.entry_price if self.entry_price > 0 else 0.0


class PathRecorder:
    """Price path of one token: a point every ``step`` seconds with the high and low in between."""

    def __init__(self, mint: str, start: float, step: float):
        self.mint = mint
        self.start = start
        self.step = step
        self.points: list[list[float]] = []
        self.hi: float | None = None
        self.lo: float | None = None
        self.last: float | None = None
        self.next_sample = start + step
        self.end_reason = ""

    def observe(self, price: float, now: float) -> None:
        if price <= 0:
            return
        self.last = price
        self.hi = price if self.hi is None else max(self.hi, price)
        self.lo = price if self.lo is None else min(self.lo, price)
        while now >= self.next_sample:
            self.points.append([price, self.hi, self.lo])
            self.hi = self.lo = price
            self.next_sample += self.step

    def record(self) -> dict[str, Any]:
        return {"typ": "pfad", "mint": self.mint, "start": self.start, "schritt": self.step, "punkte": self.points, "ende": self.end_reason}


def _sol(lamports: float) -> float:
    return round(lamports / LAMPORTS_PER_SOL, 6)


# --- the trader -----------------------------------------------------------------------------------


class PaperTrader:
    def __init__(
        self,
        strategies: list[Strategy] | None = None,
        size_sol: float = 0.08,
        latency_s: float = 2.0,
        fee_bps: int = CURVE_FEE_BPS,
        record_path: str | None = None,
        on_message: Callable[[str], None] | None = None,
        message_strategies: Iterable[str] = (),
        keywords: Iterable[str] = (),
        horizon_s: float = 900.0,
        sample_s: float = 5.0,
        entry_window_s: float = 30.0,
    ):
        self.strategies = strategies if strategies is not None else list(STRATEGIES)
        self.size_lamports = int(size_sol * LAMPORTS_PER_SOL)
        self.latency_s = latency_s
        self.fee_bps = fee_bps
        self.record_path = record_path
        self.on_message = on_message
        self.message_strategies = {s.lower() for s in message_strategies}
        self.keywords = list(keywords)
        self.horizon_s = horizon_s
        self.sample_s = sample_s
        self.entry_window_s = entry_window_s
        self.engine: Any = None
        self.orders: list[Order] = []
        self.positions: dict[tuple[str, str], Position] = {}
        self.traded: set[tuple[str, str]] = set()
        self.armed: dict[tuple[str, str], float] = {}  # (tier, mint) -> alert time
        self.paths: dict[str, PathRecorder] = {}
        self.first_entry: dict[str, float] = {}
        self.last_info: dict[str, dict[str, Any]] = {}  # mint -> numbers from the latest evaluation
        self.rug: set[str] = set()
        self.closed: list[dict[str, Any]] = []
        self.stats = {"kauf": 0, "verkauf": 0, "offen": 0, "pnl_sol": 0.0, "pfade": 0, "uebersprungen": 0}
        self._lock = threading.Lock()

    def attach(self, engine: Any) -> None:
        self.engine = engine

    # --- helpers ---------------------------------------------------------------------------------
    def _state(self, mint: str) -> Any:
        return self.engine.tokens.get(mint) if self.engine is not None else None

    def _write(self, rec: dict[str, Any]) -> None:
        if not self.record_path:
            return
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
        with self._lock, open(self.record_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _say(self, strategy: str, text: str) -> None:
        if self.on_message is None or strategy.lower() not in self.message_strategies:
            return
        try:
            self.on_message(text)
        except Exception as exc:  # noqa: BLE001
            print(f"Papier-Nachricht fehlgeschlagen: {exc!r}")

    def _narrative(self, state: Any, feats: Any, now: float) -> tuple[int, list[str]]:
        copycat = False
        if self.engine is not None and getattr(self.engine, "names", None) is not None:
            copycat = self.engine.names.is_copycat(state.mint, state.create.name, state.create.symbol, now)
        socials = getattr(feats, "socials_count", None) if feats is not None else None
        return narrative_score(state.create.name, state.create.symbol, state.metadata, socials, copycat, self.keywords)

    def _info(self, state: Any, report: QuickReport, feats: Any, now: float) -> dict[str, Any]:
        score, reasons = self._narrative(state, feats, now)
        info = {
            "wort": report.word,
            "flags": list(report.flags),
            "score": report.score,
            "mc_sol": report.mc_sol,
            "alter_s": round(now - state.created_at, 1),
            "aussen_kaeufer": getattr(feats, "unique_outside_buyers", None),
            "dev_verkauft": getattr(feats, "dev_sold_share", None),
            "bundle": getattr(feats, "creation_window_share", None),
            "narrativ": score,
            "narrativ_grund": reasons,
            "socials": getattr(feats, "socials_count", None),
            "name": state.create.name or None,
            "symbol": state.create.symbol or None,
            "profil": getattr(state, "profil", None),  # holder rise, similarity, checkpoint vectors: `profil bauen --papier` reads them
            "thema": getattr(state, "narrativ", None),  # theme wave of the launch stream (OQ-028), record-only
        }
        return info

    def _filters_ok(self, s: Strategy, info: dict[str, Any], state: Any) -> tuple[bool, str]:
        if info["wort"] in ("RUG", "TOT", "?") or state.curve is None or state.complete:
            return False, "Urteil " + info["wort"]
        if not state.curve.quote_is_sol:
            return False, "keine SOL-Kurve"  # curve math and prices below assume lamports as quote units
        if s.dev_must_hold and (info["dev_verkauft"] or 0.0) > 0:
            return False, "Dev hat verkauft"
        if s.max_bundle is not None and (info["bundle"] or 0.0) > s.max_bundle:
            return False, "Bundle"
        if s.min_outside_buyers is not None and (info["aussen_kaeufer"] or 0) < s.min_outside_buyers:
            return False, "zu wenige Käufer"
        if s.min_narrative is not None and info["narrativ"] < s.min_narrative:
            return False, f"Narrativ {info['narrativ']}"
        if s.no_warnings and any(f.split(" ")[0] in GO_BLOCKING_FLAGS or f.startswith("BUNDLE") for f in info["flags"]):
            return False, "Warnung"
        return True, ""

    # --- hooks from the engine ---------------------------------------------------------------------
    def on_alert(self, alert: Any) -> None:
        now = alert.state.last_eval or time.time()
        if alert.tier == "RUG":
            self.rug.add(alert.state.mint)
            return
        if alert.tier in ("BLICK", "GO"):
            self.armed[(alert.tier, alert.state.mint)] = now
            feats = alert.report.verdict.features if alert.report.verdict is not None else None
            self._consider(alert.state, alert.report, feats, now, alert.tier)

    def on_evaluate(self, state: Any, report: QuickReport, feats: Any, now: float) -> None:
        info = self._info(state, report, feats, now)
        self.last_info[state.mint] = info
        if report.word in ("RUG", "TOT"):
            self.rug.add(state.mint)
        self._consider(state, report, feats, now, "FRÜH", info)
        for tier in ("BLICK", "GO"):
            armed_at = self.armed.get((tier, state.mint))
            if armed_at is not None and now - armed_at <= self.entry_window_s:
                self._consider(state, report, feats, now, tier, info)

    def _consider(self, state: Any, report: QuickReport, feats: Any, now: float, trigger: str, info: dict[str, Any] | None = None) -> None:
        if info is None:
            info = self._info(state, report, feats, now)
            self.last_info[state.mint] = info
        for s in self.strategies:
            if s.entry != trigger:
                continue
            key = (s.name, state.mint)
            if key in self.traded:
                continue
            ok, why = self._filters_ok(s, info, state)
            if not ok:
                continue
            self.traded.add(key)
            reason = trigger
            extras = []
            if s.min_narrative is not None:
                extras.append(f"Narrativ {info['narrativ']}")
            if s.dev_must_hold:
                extras.append("Dev hält")
            if s.max_bundle is not None:
                extras.append(f"Bundle {(info['bundle'] or 0) * 100:.0f} %")
            if extras:
                reason += " (" + ", ".join(extras) + ")"
            context = dict(info)
            context["preis_entscheidung"] = curve_price(state.curve) if state.curve is not None else None
            self.orders.append(Order(s.name, state.mint, now, now + self.latency_s, reason, context))

    def keep_alive(self, mint: str, now: float) -> bool:
        if any(p.mint == mint for p in self.positions.values()) or any(o.mint == mint for o in self.orders):
            return True
        first = self.first_entry.get(mint)
        return first is not None and now - first < self.horizon_s

    # --- the per-second loop ---------------------------------------------------------------------
    def on_tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self._execute_orders(now)
        self._check_positions(now)
        self._sample_paths(now)

    def _execute_orders(self, now: float) -> None:
        due = [o for o in self.orders if o.execute_at <= now]
        if not due:
            return
        self.orders = [o for o in self.orders if o.execute_at > now]
        for o in due:
            state = self._state(o.mint)
            strat = next((s for s in self.strategies if s.name == o.strategy), None)
            if state is None or state.curve is None or state.complete or strat is None:
                self.stats["uebersprungen"] += 1
                self._write({"typ": "skip", "t": now, "strategie": o.strategy, "mint": o.mint, "grund": "kein Kurvenstand mehr" if state is None or state.curve is None else "graduiert"})
                continue
            if strat.exit_on_rug and o.mint in self.rug:
                self.stats["uebersprungen"] += 1
                self._write({"typ": "skip", "t": now, "strategie": o.strategy, "mint": o.mint, "grund": "RUG vor der Ausführung"})
                continue
            tokens, sol_cost, fee = buy_on_curve(state.curve, self.size_lamports, self.fee_bps)
            if tokens <= 0:
                self.stats["uebersprungen"] += 1
                self._write({"typ": "skip", "t": now, "strategie": o.strategy, "mint": o.mint, "grund": "Kauf nicht möglich"})
                continue
            entry_price = self.size_lamports / tokens * RAW_PER_TOKEN / LAMPORTS_PER_SOL  # SOL per token, all-in
            price_now = curve_price(state.curve)
            pos = Position(o.strategy, o.mint, now, entry_price, tokens, tokens, self.size_lamports, dict(o.context), fees=fee, peak=price_now, trough=price_now, last_price=price_now)
            self.positions[(o.strategy, o.mint)] = pos
            self.first_entry.setdefault(o.mint, now)
            if o.mint not in self.paths:
                self.paths[o.mint] = PathRecorder(o.mint, now, self.sample_s)
            self.paths[o.mint].observe(price_now, now)
            self.stats["kauf"] += 1
            self.stats["offen"] = len(self.positions)
            impact = price_now / (o.context.get("preis_entscheidung") or price_now) - 1.0 if o.context.get("preis_entscheidung") else None
            rec = {
                "typ": "kauf",
                "t": now,
                "strategie": o.strategy,
                "mint": o.mint,
                "name": o.context.get("name"),
                "symbol": o.context.get("symbol"),
                "ausloeser": o.reason,
                "entschieden_t": o.placed_at,
                "latenz_s": round(now - o.placed_at, 2),
                "sol_in": _sol(self.size_lamports),
                "gebuehr_sol": _sol(fee),
                "tokens": tokens / RAW_PER_TOKEN,
                "preis": entry_price,
                "kurs": price_now,
                "mc_sol": round(price_now * SUPPLY_TOKENS, 3),
                "kontext": o.context,
            }
            if impact is not None:
                rec["kurs_seit_entscheidung"] = round(impact, 4)
            self._write(rec)
            self._say(o.strategy, f"📝 {o.strategy} KAUF {o.context.get('symbol') or o.mint[:6]} · {_sol(self.size_lamports)} SOL @ MC {price_now * SUPPLY_TOKENS:.0f} SOL · {o.reason}")

    def _check_positions(self, now: float) -> None:
        for key, pos in list(self.positions.items()):
            state = self._state(pos.mint)
            strat = next((s for s in self.strategies if s.name == pos.strategy), None)
            if strat is None:
                continue
            if state is None:
                self._close(pos, None, 1.0, "ENDE", now, immediate=True)
                continue
            if state.curve is not None:
                pos.last_price = curve_price(state.curve)
                pos.peak = max(pos.peak, pos.last_price)
                pos.trough = min(pos.trough, pos.last_price)
            if state.complete:
                self._close(pos, state, 1.0, "GRAD", now, immediate=True)
                continue
            if pos.pending_exit is not None:
                reason, share, at = pos.pending_exit
                if now >= at:
                    pos.pending_exit = None
                    self._close(pos, state, share, reason, now, immediate=True)
                continue
            m = pos.multiple
            info = self.last_info.get(pos.mint, {})
            flags = info.get("flags", [])
            exit_reason: str | None = None
            share = 1.0
            if strat.exit_on_rug and (pos.mint in self.rug or info.get("wort") in ("RUG", "TOT")):
                exit_reason = "RUG"
            elif strat.exit_on_dev_sell and any(f.startswith(("DEV-RAUS", "DEV-DUMP")) for f in flags):
                exit_reason = "DEV-RAUS"
            elif strat.sl is not None and m <= 1.0 - strat.sl:
                exit_reason = f"SL −{strat.sl * 100:.0f} %"
            elif strat.tp is not None and m >= strat.tp:
                exit_reason = f"TP {strat.tp:g}x"
            elif strat.partial_tp is not None and not pos.partial_done and m >= strat.partial_tp:
                exit_reason, share = f"TEIL {strat.partial_tp:g}x", strat.partial_share
            elif strat.trail is not None:
                if m >= strat.trail_arm:
                    pos.trail_armed = True
                if pos.trail_armed and pos.last_price <= pos.peak * (1.0 - strat.trail):
                    exit_reason = f"TRAIL −{strat.trail * 100:.0f} % vom Hoch {pos.peak / pos.entry_price:.2f}x"
            if exit_reason is None and now - pos.opened_at >= strat.max_hold_s:
                exit_reason = f"ZEIT {strat.max_hold_s / 60:.0f} min"
            if exit_reason is not None:
                # a real sell lands latency_s later, on whatever the curve looks like then
                pos.pending_exit = (exit_reason, share, now + self.latency_s)

    def _close(self, pos: Position, state: Any, share: float, reason: str, now: float, immediate: bool = False) -> None:
        tokens = pos.tokens if share >= 1.0 else int(pos.tokens * share)
        if state is not None and state.curve is not None:
            net, fee = sell_on_curve(state.curve, tokens, self.fee_bps)
            price_now = curve_price(state.curve)
        else:
            gross = int(tokens * pos.last_price * LAMPORTS_PER_SOL / RAW_PER_TOKEN)
            fee = gross * self.fee_bps // 10_000
            net, price_now = gross - fee, pos.last_price
        pos.tokens -= tokens
        pos.sol_out += net
        pos.fees += fee
        if reason.startswith("TEIL"):
            pos.partial_done = True
        final = pos.tokens <= 0 or share >= 1.0
        pnl = pos.sol_out - pos.sol_in if final else None
        rec = {
            "typ": "verkauf",
            "t": now,
            "strategie": pos.strategy,
            "mint": pos.mint,
            "symbol": pos.context.get("symbol"),
            "anteil": round(tokens / pos.tokens_initial, 3) if pos.tokens_initial else 1.0,
            "grund": reason,
            "sol_out": _sol(net),
            "gebuehr_sol": _sol(fee),
            "kurs": price_now,
            "mc_sol": round(price_now * SUPPLY_TOKENS, 3),
            "vielfaches": round(price_now / pos.entry_price, 4) if pos.entry_price else None,
            "hoch": round(pos.peak / pos.entry_price, 4) if pos.entry_price else None,
            "tief": round(pos.trough / pos.entry_price, 4) if pos.entry_price and pos.trough != float("inf") else None,
            "dauer_s": round(now - pos.opened_at, 1),
            "abgeschlossen": final,
        }
        if final:
            rec["pnl_sol"] = _sol(pnl)
            rec["pnl_pct"] = round(pnl / pos.sol_in * 100, 2) if pos.sol_in else None
            rec["gebuehren_gesamt_sol"] = _sol(pos.fees)
            self.positions.pop((pos.strategy, pos.mint), None)
            self.closed.append(rec)
            self.stats["verkauf"] += 1
            self.stats["pnl_sol"] = round(self.stats["pnl_sol"] + pnl / LAMPORTS_PER_SOL, 6)
            self.stats["offen"] = len(self.positions)
            self._say(pos.strategy, f"📝 {pos.strategy} VERKAUF {pos.context.get('symbol') or pos.mint[:6]} · {pnl / pos.sol_in * 100:+.0f} % · {reason} · {(now - pos.opened_at) / 60:.1f} min")
        self._write(rec)

    def _sample_paths(self, now: float) -> None:
        for mint, path in list(self.paths.items()):
            state = self._state(mint)
            if state is not None and state.curve is not None:
                path.observe(curve_price(state.curve), now)
            open_here = any(p.mint == mint for p in self.positions.values()) or any(o.mint == mint for o in self.orders)
            expired = now - path.start >= self.horizon_s
            gone = state is None or state.complete
            if (expired and not open_here) or (gone and not open_here):
                path.end_reason = "graduiert" if state is not None and state.complete else ("Horizont" if expired else "Token weg")
                self._write(path.record())
                self.stats["pfade"] += 1
                del self.paths[mint]
                self.first_entry.pop(mint, None)

    def status_line(self) -> str:
        s = self.stats
        return f"Papier: {s['kauf']} Käufe, {s['verkauf']} abgeschlossen, {s['offen']} offen, Summe {s['pnl_sol']:+.4f} SOL, übersprungen {s['uebersprungen']}"


# --- the report -----------------------------------------------------------------------------------


def load_paper(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _trades_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join buy and final sale per (strategy, mint) into one trade row."""
    buys: dict[tuple[str, str], dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    for r in records:
        if r.get("typ") == "kauf":
            buys[(r["strategie"], r["mint"])] = r
        elif r.get("typ") == "verkauf" and r.get("abgeschlossen"):
            b = buys.get((r["strategie"], r["mint"]))
            if b is None:
                continue
            trades.append(
                {
                    "strategie": r["strategie"],
                    "mint": r["mint"],
                    "symbol": r.get("symbol") or b.get("symbol"),
                    "t_kauf": b["t"],
                    "t_verkauf": r["t"],
                    "preis": b["preis"],
                    "sol_in": b["sol_in"],
                    "pnl_sol": r.get("pnl_sol", 0.0),
                    "pnl_pct": r.get("pnl_pct", 0.0) or 0.0,
                    "grund": r.get("grund", ""),
                    "hoch": r.get("hoch"),
                    "dauer_s": r.get("dauer_s"),
                    "kontext": b.get("kontext", {}),
                }
            )
    return trades


def _bootstrap_ci(values: list[float], n: int = 2000, seed: int = 7) -> tuple[float, float]:
    if len(values) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    k = len(values)
    for _ in range(n):
        sample = [values[rng.randrange(k)] for _ in range(k)]
        means.append(sum(sample) / k)
    means.sort()
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def _max_drawdown(pnls: list[float]) -> float:
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _cash_replay(trades: list[dict[str, Any]], cash: float, size: float) -> tuple[float, int, int]:
    """Replay one strategy's trades with a fixed bankroll: (end cash, taken, skipped)."""
    events = sorted(trades, key=lambda t: t["t_kauf"])
    free = cash
    open_until: list[tuple[float, float]] = []  # (close time, cash returned)
    taken = skipped = 0
    for t in events:
        open_until.sort()
        while open_until and open_until[0][0] <= t["t_kauf"]:
            free += open_until.pop(0)[1]
        if free + 1e-12 >= size:
            free -= size
            open_until.append((t["t_verkauf"], size + t["pnl_sol"] / t["sol_in"] * size))
            taken += 1
        else:
            skipped += 1
    for _, back in open_until:
        free += back
    return free, taken, skipped


GRID_TP = (1.5, 2.0, 3.0, 5.0)
GRID_SL = (0.25, 0.4, 0.6, None)
GRID_HOLD = (120.0, 300.0, 600.0, 900.0)


def simulate_rule(path: dict[str, Any], t_entry: float, entry_price: float, tp: float | None, sl: float | None, hold_s: float, fee_bps: int = CURVE_FEE_BPS) -> tuple[float, str] | None:
    """Result (fraction, e.g. +0.5) of a TP/SL/time rule on a recorded path from ``t_entry``. SL wins ties."""
    step = path["schritt"]
    start = path["start"]
    pts = path["punkte"]
    if not pts or entry_price <= 0:
        return None
    i0 = max(0, int((t_entry - start) / step))
    if i0 >= len(pts):
        return None
    fee = 1.0 - fee_bps / 10_000
    last_close = pts[i0][0]
    for i in range(i0, len(pts)):
        close, hi, lo = pts[i]
        if i == i0:
            hi = lo = close  # the entry bucket also holds prices from before the entry: only its close lies after it
        if start + (i + 1) * step - t_entry > hold_s:
            break
        if sl is not None and lo <= entry_price * (1.0 - sl):
            return (1.0 - sl) * fee - 1.0, "SL"
        if tp is not None and hi >= entry_price * tp:
            return tp * fee - 1.0, "TP"
        last_close = close
    return last_close / entry_price * fee - 1.0, "ZEIT"


def what_if_grid(trades: list[dict[str, Any]], paths: dict[str, dict[str, Any]]) -> dict[tuple[float | None, float | None, float], list[float]]:
    grid: dict[tuple[float | None, float | None, float], list[float]] = {}
    for t in trades:
        path = paths.get(t["mint"])
        if path is None:
            continue
        for tp in GRID_TP:
            for sl in GRID_SL:
                for hold in GRID_HOLD:
                    res = simulate_rule(path, t["t_kauf"], t["preis"], tp, sl, hold)
                    if res is not None:
                        grid.setdefault((tp, sl, hold), []).append(res[0])
    return grid


def _fmt_cell(tp: float | None, sl: float | None, hold: float) -> str:
    return f"TP {tp:g}x / SL {'—' if sl is None else f'−{sl * 100:.0f} %'} / {hold / 60:.0f} min"


def paper_report(records: list[dict[str, Any]], cash: float | None = 0.25, size: float | None = None, min_trades: int = 10) -> str:
    trades = _trades_from_records(records)
    paths = {r["mint"]: r for r in records if r.get("typ") == "pfad"}
    lines: list[str] = []
    if not trades:
        lines.append("Noch keine abgeschlossenen Papier-Trades in der Datei.")
        buys = sum(1 for r in records if r.get("typ") == "kauf")
        if buys:
            lines.append(f"{buys} Käufe sind noch offen oder ohne Verkaufszeile.")
        return "\n".join(lines)
    by_strategy: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        by_strategy.setdefault(t["strategie"], []).append(t)
    t_min = min(t["t_kauf"] for t in trades)
    t_max = max(t["t_verkauf"] for t in trades)
    n_tokens = len({t["mint"] for t in trades})
    lines.append(f"Papier-Trades: {len(trades)} auf {n_tokens} Token, Zeitraum {(t_max - t_min) / 3600:.1f} h, {len(by_strategy)} Strategien")
    if size is None:
        size = trades[0]["sol_in"]
    lines.append("")
    lines.append(f"{'Strategie':<14}{'n':>5}{'Treffer':>9}{'Ø %':>8}{'Median':>8}{'Summe SOL':>11}{'95 %-KI Ø %':>18}{'max. DD SOL':>13}{'Kasse':>9}  Ausstiege")
    ranking: list[tuple[str, float, float, int]] = []
    for name, ts in sorted(by_strategy.items(), key=lambda kv: -sum(t["pnl_sol"] for t in kv[1])):
        pcts = [t["pnl_pct"] for t in ts]
        pnls = [t["pnl_sol"] for t in sorted(ts, key=lambda t: t["t_verkauf"])]
        hit = sum(1 for p in pcts if p > 0) / len(pcts)
        mean = sum(pcts) / len(pcts)
        med = statistics.median(pcts)
        lo, hi = _bootstrap_ci(pcts) if len(pcts) >= min_trades else (float("nan"), float("nan"))
        dd = _max_drawdown(pnls)
        reasons: dict[str, int] = {}
        for t in ts:
            head = t["grund"].split(" ")[0]
            reasons[head] = reasons.get(head, 0) + 1
        reason_txt = ", ".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]))
        cash_txt = ""
        if cash:
            end, taken, skipped = _cash_replay(ts, cash, size)
            cash_txt = f"{end:.3f}"
        ci_txt = f"[{lo:+.1f}, {hi:+.1f}]" if not math.isnan(lo) else "(n < 10)"
        lines.append(f"{name:<14}{len(ts):>5}{hit * 100:>8.0f}%{mean:>+8.1f}{med:>+8.1f}{sum(pnls):>+11.4f}{ci_txt:>18}{dd:>13.4f}{cash_txt:>9}  {reason_txt}")
        ranking.append((name, mean, lo, len(ts)))
    lines.append("")
    if cash:
        lines.append(f"Kasse = Endstand in SOL, wenn du mit {cash} SOL Kasse und {size} SOL je Trade nur so viele Positionen offen hältst, wie die Kasse hergibt.")
    lines.append("95 %-KI = Bootstrap-Konfidenzintervall des mittleren Ergebnisses je Trade. Erst wenn die untere Grenze über 0 liegt, hat eine Strategie nachweislich Kante.")
    proven = [r for r in ranking if not math.isnan(r[2]) and r[2] > 0]
    if proven:
        best = max(proven, key=lambda r: r[2])
        lines.append(f"Kandidat: {best[0]} (Ø {best[1]:+.1f} %, untere KI-Grenze {best[2]:+.1f} %, n = {best[3]}).")
    else:
        best_mean = max(ranking, key=lambda r: r[1])
        lines.append(f"Noch keine Strategie mit unterer KI-Grenze über 0. Bester Mittelwert: {best_mean[0]} mit {best_mean[1]:+.1f} % bei n = {best_mean[3]}.")
        need = []
        for name, mean, _, n in ranking:
            pcts = [t["pnl_pct"] for t in by_strategy[name]]
            if mean > 0 and len(pcts) >= 2:
                sd = statistics.pstdev(pcts)
                need.append((name, int(math.ceil((1.96 * sd / mean) ** 2)) if mean else 0))
        if need:
            lines.append("Grob nötige Trades für einen Nachweis (bei gleichbleibendem Mittelwert): " + ", ".join(f"{n} {k}" for n, k in need[:4]))
    # what-if grid on the recorded paths
    if paths:
        lines.append("")
        lines.append("Was-wäre-wenn auf den aufgezeichneten Pfaden (Einstieg wie gehandelt, Verkauf zum Zielkurs minus Gebühr, ohne eigenen Preiseinfluss):")
        for name, ts in by_strategy.items():
            with_path = [t for t in ts if t["mint"] in paths]
            if len(with_path) < min_trades:
                continue
            grid = what_if_grid(with_path, paths)
            cells = [(k, sum(v) / len(v), sum(1 for x in v if x > 0) / len(v), len(v)) for k, v in grid.items() if len(v) >= min_trades]
            if not cells:
                continue
            cells.sort(key=lambda c: -c[1])
            k, mean, hit, n = cells[0]
            line = f"  {name}: beste Regel {_fmt_cell(*k)} → Ø {mean * 100:+.1f} %, Treffer {hit * 100:.0f} % (n = {n})"
            # holdout: best cell on the first half of the entries, applied to the second half
            ordered = sorted(with_path, key=lambda t: t["t_kauf"])
            half = len(ordered) // 2
            if half >= 5:
                g1 = what_if_grid(ordered[:half], paths)
                g2 = what_if_grid(ordered[half:], paths)
                c1 = [(kk, sum(v) / len(v)) for kk, v in g1.items() if len(v) >= 5]
                if c1:
                    kk, m1 = max(c1, key=lambda c: c[1])
                    v2 = g2.get(kk, [])
                    if v2:
                        line += f"; die beste Regel der ersten Hälfte ({_fmt_cell(*kk)}, Ø {m1 * 100:+.1f} %) bringt in der zweiten Hälfte Ø {sum(v2) / len(v2) * 100:+.1f} %"
            lines.append(line)
    lines.append("")
    lines.append("Jede Zahl hier ist Papier: ohne fehlgeschlagene Transaktionen, ohne Priority-Fees, mit fester Latenz. Echt wird es eher schlechter.")
    return "\n".join(lines)


# --- looking back at past calls from chain history --------------------------------------------------


def fetch_trade_path(rpc: Any, mint: str, t_from: float, t_to: float, max_pages: int = 5) -> list[tuple[float, float, BondingCurveState]]:
    """(time, price, curve) after every successful curve trade of ``mint`` between ``t_from`` and ``t_to``.

    Uses getSignaturesForAddress on the mint (newest first, paged) and getTransaction in batches.
    """
    from .pump import TOKEN_TOTAL_SUPPLY as SUPPLY

    sigs: list[dict[str, Any]] = []
    before = None
    for _ in range(max_pages):
        page = rpc.get_signatures(mint, limit=1000, before=before)
        if not page:
            break
        sigs.extend(page)
        before = page[-1].get("signature")
        oldest = page[-1].get("blockTime")
        if oldest is not None and oldest < t_from - 5:
            break
        if len(page) < 1000:
            break
    wanted = [s["signature"] for s in sigs if s.get("err") is None and s.get("blockTime") is not None and t_from - 5 <= s["blockTime"] <= t_to]
    out: list[tuple[float, float, BondingCurveState]] = []
    for i in range(0, len(wanted), 100):
        txs = rpc.get_transactions(wanted[i : i + 100])
        for sig in wanted[i : i + 100]:
            parsed = parse_transaction(sig, txs.get(sig))
            if parsed is None or parsed.failed:
                continue
            for tr in parsed.trades:
                if tr.mint != mint or tr.virtual_token_reserves <= 0:
                    continue
                curve = BondingCurveState(
                    virtual_token_reserves=tr.virtual_token_reserves,
                    virtual_quote_reserves=tr.virtual_sol_reserves,
                    real_token_reserves=tr.real_token_reserves,
                    real_quote_reserves=tr.real_sol_reserves,
                    token_total_supply=SUPPLY,
                    complete=False,
                )
                t = float(tr.timestamp or parsed.block_time or 0)
                out.append((t, curve_price(curve), curve))
    out.sort(key=lambda x: x[0])
    return out


def path_from_trades(trades: list[tuple[float, float, Any]], start: float, step: float = 5.0, horizon_s: float = 900.0) -> dict[str, Any]:
    rec = PathRecorder("", start, step)
    for t, price, _ in trades:
        if t < start:
            rec.last = price
            continue
        if t > start + horizon_s:
            break
        rec.observe(price, t)
    # carry the last price to the end of the horizon so time exits have a close
    if rec.last is not None:
        rec.observe(rec.last, start + horizon_s)
    return {"typ": "pfad", "mint": "", "start": start, "schritt": step, "punkte": rec.points, "ende": "Rückblick"}


def look_back(rpc: Any, calls: list[tuple[str, float]], size_sol: float = 0.08, latency_s: float = 2.0, horizon_s: float = 900.0) -> str:
    """For past calls (mint, unix time): what every grid rule would have made, entering ``latency_s`` after the call."""
    lines: list[str] = []
    results: dict[tuple[float | None, float | None, float], list[float]] = {}
    peaks: list[float] = []
    for mint, t_call in calls:
        try:
            trades = fetch_trade_path(rpc, mint, t_call - 120, t_call + horizon_s + 5)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{mint[:8]}…: Historie nicht ladbar ({exc})")
            continue
        t_entry = t_call + latency_s
        before = [x for x in trades if x[0] <= t_entry]
        if not before:
            lines.append(f"{mint[:8]}…: kein Kurvenstand vor dem Einstieg gefunden (Historie zu kurz)")
            continue
        _, _, curve = before[-1]  # the curve as it stood when our order would have landed, not the next trade after it
        tokens, _, _ = buy_on_curve(curve, int(size_sol * LAMPORTS_PER_SOL))
        if tokens <= 0:
            lines.append(f"{mint[:8]}…: Kauf nicht möglich")
            continue
        entry_price = size_sol / (tokens / RAW_PER_TOKEN)
        path = path_from_trades(trades, t_entry, 5.0, horizon_s)
        later = [p for t, p, _ in trades if t_entry <= t <= t_entry + horizon_s]
        peak = max(later) / entry_price if later else 0.0
        peaks.append(peak)
        best_txt = ""
        for tp in GRID_TP:
            for sl in GRID_SL:
                for hold in GRID_HOLD:
                    res = simulate_rule(path, t_entry, entry_price, tp, sl, hold)
                    if res is not None:
                        results.setdefault((tp, sl, hold), []).append(res[0])
        r3 = simulate_rule(path, t_entry, entry_price, 3.0, 0.4, 600.0)
        if r3 is not None:
            best_txt = f"TP 3x / SL −40 % / 10 min → {r3[0] * 100:+.0f} % ({r3[1]})"
        lines.append(f"{mint[:8]}… Call {time.strftime('%d.%m. %H:%M', time.localtime(t_call))}: Einstieg {latency_s:.0f} s später bei MC {entry_price * SUPPLY_TOKENS:.0f} SOL, Hoch danach {peak:.2f}x; {best_txt}")
    if peaks:
        lines.append("")
        lines.append(f"{len(peaks)} Calls: Median-Hoch nach dem Einstieg {statistics.median(peaks):.2f}x, {sum(1 for p in peaks if p >= 2) / len(peaks) * 100:.0f} % erreichen 2x, {sum(1 for p in peaks if p >= 3) / len(peaks) * 100:.0f} % erreichen 3x")
        cells = [(k, sum(v) / len(v), sum(1 for x in v if x > 0) / len(v), len(v)) for k, v in results.items()]
        cells.sort(key=lambda c: -c[1])
        for k, mean, hit, n in cells[:5]:
            lines.append(f"  {_fmt_cell(*k)} → Ø {mean * 100:+.1f} %, Treffer {hit * 100:.0f} % (n = {n})")
        worst = cells[-1]
        lines.append(f"  schlechteste Regel: {_fmt_cell(*worst[0])} → Ø {worst[1] * 100:+.1f} %")
    return "\n".join(lines)


def parse_calls_file(path: str) -> list[tuple[str, float]]:
    """Lines "mint unix-time" or "mint 2026-09-26T18:30:00" (UTC); '#' comments allowed."""
    import datetime as dt

    calls: list[tuple[str, float]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.replace(",", " ").split()
            if len(parts) < 2:
                continue
            mint, when = parts[0], parts[1]
            try:
                t = float(when)
            except ValueError:
                try:
                    parsed = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                t = parsed.timestamp()
            calls.append((mint, t))
    return calls


__all__ = [
    "CURVE_FEE_BPS",
    "STRATEGIES",
    "PaperTrader",
    "Strategy",
    "buy_on_curve",
    "curve_price",
    "fetch_trade_path",
    "load_paper",
    "look_back",
    "paper_report",
    "parse_calls_file",
    "sell_on_curve",
    "simulate_rule",
    "strategies_by_name",
]
