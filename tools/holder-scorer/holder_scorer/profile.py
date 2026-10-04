"""Profil: Frühvektor der ersten Sekunden, Referenzprofil gespeicherter guter Coins, Ähnlichkeit.

Kausale Idee: Ein Coin, der in den ersten Sekunden fortlaufend *neue Halter* gewinnt, hat Nachfrage, die
nicht nur vom Dev oder einem Bundle stammt. Ob dieses Muster später eine positive Netto-Rendite liefert, ist
eine Hypothese; das Profil macht sie prüfbar statt sie zu glauben:

1. ``early_vector`` misst zu einem festen Zeitpunkt nach dem ersten Trade (Checkpoint 10/20/30/45 s) nur
   Dinge, die zu diesem Zeitpunkt bekannt waren: Halter, Halter-Anstieg der letzten 15 s, Käufer, Verkäufe,
   Zufluss, MC, Kaufgrößen, Dev-Anteil, Käufer im ersten Slot. Kein Look-ahead.
2. ``build_profile`` nimmt gespeicherte Coins (Tape aus ``live --tape``, Records aus ``--record``, Papier aus
   ``--paper``, optional eine Mint-Liste per RPC), gibt jedem ein Rendite-Label mit derselben Kurvenmathematik
   wie ``tape report`` (Einstieg t0+60 s, Ausstieg +180 s, Kosten) und bildet je Checkpoint Bänder (10.–90.
   Perzentil der *guten* Coins). Merkmale, deren Band die *schlechten* Coins ausschließt, zählen mehr.
3. ``similarity`` sagt für einen neuen Coin am gleichen Checkpoint: welcher Anteil der Merkmale liegt im
   Band guter Coins. Der Live-Modus verlangt für GO einen Halter-Anstieg in den letzten Sekunden und, wenn ein
   Profil geladen ist, eine Ähnlichkeit über der Schwelle.

Nutzungsvolumen: Der Live-Vektor entsteht aus den ohnehin abonnierten Log-Trades (null zusätzliche
RPC-Aufrufe). Nur ``profil bauen --mints`` lädt Historie per RPC, begrenzt durch ``--max-mints``/``--max-pages``
und mit Schätzung vorab (``--dry-run``).

Ehrlich: Mit wenigen Dutzend gespeicherten Coins sind die Bänder grob. Deshalb speichert das Profil seine
Datenbasis, und ``--split`` prüft auf der zeitlich späteren Hälfte, ob die Ähnlichkeit überhaupt mit der
Rendite zusammenhängt (sonst ist der Filter nur Lärm).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import time
from dataclasses import dataclass
from typing import Any, Iterable

from .features import DUST_TOKENS
from .pump import LAMPORTS_PER_SOL, TOKEN_TOTAL_SUPPLY, TradeEvent

PROFILE_VERSION = 1
CHECKPOINTS = (10.0, 20.0, 30.0, 45.0, 60.0, 90.0)
RISE_WINDOW_S = 15.0
MIN_GOOD = 5  # unter dieser Zahl guter Coins je Checkpoint gibt es kein Band
MIN_BAD_FOR_WEIGHTS = 5
DEFAULT_ENTRY_AGE_S = 60.0  # Label: Einstieg 60 s nach dem ersten Trade (nach dem 45-s-Checkpoint)
DEFAULT_HORIZON_S = 180.0  # ... Ausstieg 180 s später = 240 s, das Standard-Beobachtungsfenster von `live`
DEFAULT_SIZE_SOL = 0.08
DEFAULT_QUANTILE = 0.10
DEFAULT_MIN_SIMILARITY = 0.7
CENSOR_SLACK_S = 30.0  # endet das Tape mehr als 30 s vor dem Ausstieg (ohne Graduation), ist das Label zensiert

FEATURES = (
    "holders",
    "holders_rise",
    "buyers",
    "buyers_rise",
    "sells",
    "sell_share",
    "inflow_sol",
    "inflow_rise_sol",
    "mc_sol",
    "median_buy_sol",
    "max_buy_share",
    "dev_share",
    "first_slot_buyers",
)
FEATURE_TEXT = {
    "holders": "Halter",
    "holders_rise": "Halter+",
    "buyers": "Käufer",
    "buyers_rise": "Käufer+",
    "sells": "Verkäufe",
    "sell_share": "Verkaufsanteil",
    "inflow_sol": "Zufluss",
    "inflow_rise_sol": "Zufluss+",
    "mc_sol": "MC",
    "median_buy_sol": "Kaufgröße",
    "max_buy_share": "Größter Kauf",
    "dev_share": "Dev-Anteil",
    "first_slot_buyers": "Slot-0-Käufer",
}


# --- Ticks: die kleinste gemeinsame Form eines Trades (Live-Events, Tape-Zeilen, Kettenhistorie) ---------------


@dataclass(frozen=True)
class Tick:
    ts: float  # Blockzeit in Sekunden
    user: str
    buy: bool
    sol: int  # Lamports (Quote)
    tok: int  # Token in Rohstücken
    v_sol: int
    v_tok: int
    r_sol: int = 0
    r_tok: int = 0
    slot: int = 0


def ticks_from_trades(trades: Iterable[TradeEvent]) -> list[Tick]:
    out: list[Tick] = []
    for t in trades:
        ts = t.timestamp or t.block_time or 0
        if not ts or t.virtual_token_reserves <= 0:
            continue
        out.append(
            Tick(
                float(ts), t.user, bool(t.is_buy), int(t.quote_lamports), int(t.token_amount),
                int(t.virtual_sol_reserves), int(t.virtual_token_reserves), int(t.real_sol_reserves or 0),
                int(t.real_token_reserves or 0), int(t.slot or 0),
            )
        )
    out.sort(key=lambda x: (x.ts, x.slot))
    return out


def ticks_from_rows(rows: Iterable[dict[str, Any]]) -> list[Tick]:
    """Tape-Zeilen (``live --tape``) als Ticks."""
    out: list[Tick] = []
    for r in rows:
        ts = r.get("ts") or int(r.get("seen_at") or 0)
        if not ts or r.get("vT") is None or int(r["vT"]) <= 0:
            continue
        out.append(
            Tick(
                float(int(ts)), str(r.get("user") or ""), bool(r.get("buy")), int(r.get("sol") or 0), int(r.get("tok") or 0),
                int(r["vS"]), int(r["vT"]), int(r.get("rS") or 0), int(r.get("rT") or 0), int(r.get("slot") or 0),
            )
        )
    out.sort(key=lambda x: (x.ts, x.slot))
    return out


def rows_from_ticks(mint: str, ticks: Iterable[Tick]) -> list[dict[str, Any]]:
    """Ticks als Tape-Zeilen, damit ``replay.simulate`` das Rendite-Label rechnen kann."""
    return [
        {"mint": mint, "ts": int(t.ts), "slot": t.slot, "buy": t.buy, "user": t.user, "sol": t.sol, "tok": t.tok, "vS": t.v_sol, "vT": t.v_tok, "rS": t.r_sol, "rT": t.r_tok}
        for t in ticks
    ]


# --- Frühvektor -----------------------------------------------------------------------------------------------------


def early_vector(ticks: list[Tick], at: float, dev: str | None = None, window_s: float = RISE_WINDOW_S) -> dict[str, Any] | None:
    """Der Zustand des Coins zur Blockzeit ``at``, nur aus Ticks mit ``ts <= at`` (kein Look-ahead).

    ``dev`` ist der Creator; fehlt er, gilt der Käufer des ersten Kaufs als Dev (Näherung für alte Tapes).
    """
    if not ticks:
        return None
    t0 = ticks[0].ts
    if at < t0:
        return None
    upto = [t for t in ticks if t.ts <= at]
    if not upto:
        return None
    if dev is None:
        first_buy = next((t for t in upto if t.buy), None)
        dev = first_buy.user if first_buy else ""

    def holders_at(limit: float) -> int:
        bal: dict[str, int] = {}
        for t in upto:
            if t.ts > limit:
                break
            bal[t.user] = bal.get(t.user, 0) + (t.tok if t.buy else -t.tok)
        return sum(1 for u, v in bal.items() if u != dev and v > DUST_TOKENS)

    h_now = holders_at(at)
    h_prev = holders_at(at - window_s)
    h_prev2 = holders_at(at - 2 * window_s)
    outside = [t for t in upto if t.user != dev]
    buys = [t for t in outside if t.buy]
    sells = [t for t in outside if not t.buy]
    seen_before = {t.user for t in buys if t.ts <= at - window_s}
    buyers_rise = len({t.user for t in buys if t.ts > at - window_s} - seen_before)
    inflow = sum(t.sol if t.buy else -t.sol for t in outside) / LAMPORTS_PER_SOL
    inflow_rise = sum(t.sol if t.buy else -t.sol for t in outside if t.ts > at - window_s) / LAMPORTS_PER_SOL
    last = upto[-1]
    mc = last.v_sol / last.v_tok * TOKEN_TOTAL_SUPPLY / LAMPORTS_PER_SOL if last.v_tok > 0 else 0.0
    sizes = [t.sol / LAMPORTS_PER_SOL for t in buys]
    total_buy = sum(sizes)
    dev_bal = sum(t.tok if t.buy else -t.tok for t in upto if t.user == dev)
    slots = [t.slot for t in upto if t.slot > 0]
    first_slot = min(slots) if slots else None
    return {
        "age_s": round(at - t0, 3),
        "t0": t0,
        "n_trades": len(upto),
        "holders": h_now,
        "holders_rise": h_now - h_prev,
        "holders_rise_prev": h_prev - h_prev2,
        "buyers": len({t.user for t in buys}),
        "buyers_rise": buyers_rise,
        "sells": len(sells),
        "sell_share": round(len(sells) / (len(buys) + len(sells)), 4) if outside else 0.0,
        "inflow_sol": round(inflow, 6),
        "inflow_rise_sol": round(inflow_rise, 6),
        "mc_sol": round(mc, 4),
        "median_buy_sol": round(statistics.median(sizes), 6) if sizes else 0.0,
        "max_buy_share": round(max(sizes) / total_buy, 4) if total_buy > 0 else 0.0,
        "dev_share": round(max(0, dev_bal) / TOKEN_TOTAL_SUPPLY, 6),
        "first_slot_buyers": len({t.user for t in buys if first_slot is not None and t.slot == first_slot}),
    }


def cp_key(cp: float) -> str:
    return f"{float(cp):g}"


def checkpoints_before(entry_age_s: float, checkpoints: Iterable[float] = CHECKPOINTS) -> tuple[float, ...]:
    """Nur Checkpoints vor dem Einstieg des Labels sind erlaubt (sonst sähe der Vektor die Zukunft des Labels)."""
    return tuple(c for c in checkpoints if c < entry_age_s)


def checkpoint_for(age_s: float, available: Iterable[float]) -> float | None:
    cps = [float(c) for c in available if float(c) <= age_s]
    return max(cps) if cps else None


def vectors_at_checkpoints(ticks: list[Tick], dev: str | None, checkpoints: Iterable[float], max_age_s: float | None = None) -> dict[str, dict[str, Any]]:
    if not ticks:
        return {}
    t0 = ticks[0].ts
    out: dict[str, dict[str, Any]] = {}
    for cp in checkpoints:
        cp = float(cp)
        if max_age_s is not None and cp > max_age_s:
            continue
        vec = early_vector(ticks, t0 + cp, dev)
        if vec is not None:
            out[cp_key(cp)] = vec
    return out


# --- Bänder, Profil, Ähnlichkeit -------------------------------------------------------------------------------------


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def build_bands(good: list[dict[str, Any]], bad: list[dict[str, Any]], quantile: float = DEFAULT_QUANTILE, features: Iterable[str] = FEATURES) -> dict[str, dict[str, Any]]:
    """Je Merkmal das Band [q, 1-q] der guten Coins; Gewicht 0,5 + 0,5 × Anteil schlechter Coins außerhalb."""
    bands: dict[str, dict[str, Any]] = {}
    for f in features:
        gv = [float(v[f]) for v in good if v.get(f) is not None]
        if len(gv) < MIN_GOOD:
            continue
        lo, hi = _quantile(gv, quantile), _quantile(gv, 1 - quantile)
        bv = [float(v[f]) for v in bad if v.get(f) is not None]
        weight, bad_outside = 1.0, None
        if len(bv) >= MIN_BAD_FOR_WEIGHTS:
            bad_outside = sum(1 for x in bv if x < lo or x > hi) / len(bv)
            weight = 0.5 + 0.5 * bad_outside
        bands[f] = {
            "lo": round(lo, 6),
            "hi": round(hi, 6),
            "med": round(statistics.median(gv), 6),
            "n": len(gv),
            "weight": round(weight, 4),
            "bad_outside": None if bad_outside is None else round(bad_outside, 4),
        }
    return bands


def profile_hash(profile: dict[str, Any]) -> str:
    payload = json.dumps(profile.get("checkpoints") or {}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def profile_from_vectors(
    good: dict[str, dict[str, dict[str, Any]]],
    bad: dict[str, dict[str, dict[str, Any]]],
    *,
    quantile: float = DEFAULT_QUANTILE,
    label_rule: str = "",
    sources: dict[str, Any] | None = None,
    checkpoints: Iterable[float] | None = None,
) -> dict[str, Any]:
    """``good``/``bad``: Mint -> {Checkpoint-Schlüssel -> Vektor}."""
    if checkpoints is None:
        keys = {k for vs in list(good.values()) + list(bad.values()) for k in vs}
        cps = sorted((float(k) for k in keys))
    else:
        cps = sorted(float(c) for c in checkpoints)
    out_cps: dict[str, dict[str, Any]] = {}
    for cp in cps:
        k = cp_key(cp)
        g = [vs[k] for vs in good.values() if k in vs]
        b = [vs[k] for vs in bad.values() if k in vs]
        bands = build_bands(g, b, quantile)
        if bands:
            out_cps[k] = {"n_good": len(g), "n_bad": len(b), "bands": bands}
    profile: dict[str, Any] = {
        "version": PROFILE_VERSION,
        "built_at": time.time(),
        "label_rule": label_rule,
        "quantile": quantile,
        "min_good": MIN_GOOD,
        "min_similarity": DEFAULT_MIN_SIMILARITY,
        "sources": sources or {},
        "good": sorted(good),
        "bad": sorted(bad),
        "checkpoints": out_cps,
    }
    profile["hash"] = profile_hash(profile)
    return profile


def profile_checkpoints(profile: dict[str, Any] | None) -> list[float]:
    if not profile:
        return []
    return sorted(float(k) for k in (profile.get("checkpoints") or {}))


def profile_usable(profile: dict[str, Any] | None) -> bool:
    return bool(profile) and bool(profile.get("checkpoints"))


def similarity(profile: dict[str, Any], vector: dict[str, Any], checkpoint: float) -> dict[str, Any] | None:
    """Gewichteter Anteil der Merkmale im Band guter Coins (0..1) am gleichen Checkpoint."""
    cp = (profile.get("checkpoints") or {}).get(cp_key(checkpoint))
    if not cp:
        return None
    total = inside = 0.0
    outside: list[str] = []
    for f, b in cp["bands"].items():
        x = vector.get(f)
        if x is None:
            continue
        w = float(b.get("weight", 1.0))
        total += w
        if b["lo"] <= float(x) <= b["hi"]:
            inside += w
        else:
            outside.append(f"{FEATURE_TEXT.get(f, f)}{'↑' if float(x) > b['hi'] else '↓'}")
    if total <= 0:
        return None
    return {"aehnlich": round(inside / total, 4), "checkpoint": checkpoint, "merkmale": len(cp["bands"]), "ausserhalb": outside, "n_gut": cp["n_good"], "n_schlecht": cp["n_bad"]}


def save_profile(profile: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False, sort_keys=True, indent=1)
        fh.write("\n")


def load_profile(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        profile = json.load(fh)
    if not isinstance(profile, dict) or profile.get("version") != PROFILE_VERSION or not isinstance(profile.get("checkpoints"), dict):
        raise ValueError(f"{path}: kein Profil der Version {PROFILE_VERSION}")
    if not profile["checkpoints"]:
        raise ValueError(f"{path}: Profil ohne Checkpoints (zu wenige gute Coins beim Bauen)")
    return profile


def describe_profile(profile: dict[str, Any]) -> str:
    lines = [
        f"Profil {profile.get('hash', '?')} · gebaut {time.strftime('%Y-%m-%d %H:%M', time.localtime(float(profile.get('built_at') or 0)))} · "
        f"{len(profile.get('good') or [])} gute, {len(profile.get('bad') or [])} schlechte Coins · Label: {profile.get('label_rule') or '?'}"
    ]
    src = profile.get("sources") or {}
    if src:
        lines.append("Quellen: " + ", ".join(f"{k} {v}" for k, v in sorted(src.items())))
    for k in sorted(profile.get("checkpoints") or {}, key=float):
        cp = profile["checkpoints"][k]
        lines.append(f"Checkpoint {k} s: {cp['n_good']} gut / {cp['n_bad']} schlecht, {len(cp['bands'])} Merkmale")
        for f, b in sorted(cp["bands"].items(), key=lambda kv: -kv[1]["weight"]):
            sep = "" if b.get("bad_outside") is None else f", schlechte außerhalb {b['bad_outside'] * 100:.0f} %"
            lines.append(f"  {FEATURE_TEXT.get(f, f):<14} {b['lo']:g} – {b['hi']:g} (Median {b['med']:g}), Gewicht {b['weight']:.2f}{sep}")
    check = profile.get("pruefung")
    if check:
        lines.append(_format_check(check))
    return "\n".join(lines)


# --- Labels ----------------------------------------------------------------------------------------------------------


def label_from_rows(rows: list[dict[str, Any]], entry_age_s: float, horizon_s: float, size_sol: float, costs: Any) -> dict[str, Any]:
    """Rendite-Label eines Coins aus seinen Tape-Zeilen: gut = graduiert oder r_cons > 0."""
    from .replay import simulate

    if not rows:
        return {"handelbar": False, "grund": "keine Zeilen"}
    rows = sorted(rows, key=lambda r: (int(r.get("slot") or 0), int(r["ts"])))
    t0 = float(min(int(r["ts"]) for r in rows))
    t_entry = t0 + entry_age_s
    t_exit = t_entry + horizon_s
    last = rows[-1]
    graduated_in_tape = int(last.get("rT") or 0) <= 0
    if int(last["ts"]) < t_exit - CENSOR_SLACK_S and not graduated_in_tape:
        return {"handelbar": None, "zensiert": True, "t0": t0, "grund": f"Tape endet {t_exit - int(last['ts']):.0f} s vor dem Ausstieg"}
    res = simulate(rows, t_entry, horizon_s, int(size_sol * LAMPORTS_PER_SOL), costs)
    if res is None:
        return {"handelbar": False, "zensiert": False, "t0": t0, "grund": "kein handelbarer Kurvenstand beim Einstieg"}
    return {
        "handelbar": True,
        "zensiert": False,
        "t0": t0,
        "r_cons": round(res["r_cons"], 6),
        "r_opt": round(res["r_opt"], 6),
        "graduiert": bool(res["graduated"]),
        "gut": bool(res["graduated"] or res["r_cons"] > 0),
    }


def label_rule_text(entry_age_s: float, horizon_s: float, size_sol: float, costs: Any) -> str:
    price = getattr(costs, "cu_price_micro", None)
    return f"gut = graduiert oder Netto-Rendite > 0 bei Einstieg t0+{entry_age_s:g} s, Ausstieg +{horizon_s:g} s, {size_sol:g} SOL, Priority {price} µLamports/CU, Kurvengebühr aus dem Trade"


def parse_mints_file(path: str) -> list[tuple[str, bool | None]]:
    """Je Zeile ``<Mint> [gut|schlecht]``; ohne Wort wird das Label aus der Historie gerechnet."""
    out: list[tuple[str, bool | None]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            label: bool | None = None
            if len(parts) > 1:
                word = parts[1].lower()
                label = True if word in ("gut", "good", "1") else False if word in ("schlecht", "bad", "0") else None
            out.append((parts[0], label))
    return out


def fetch_ticks(rpc: Any, mint: str, seconds: float, max_pages: int = 10) -> tuple[list[Tick], dict[str, Any]]:
    """Die ersten ``seconds`` eines Coins aus der Kette: Signaturen des Mints rückwärts bis zur ältesten Seite,
    dann getTransaction nur für das Fenster. Bricht ab, wenn ``max_pages`` Seiten nicht bis zum Anfang reichen."""
    from .pump import parse_transaction

    sigs: list[dict[str, Any]] = []
    before = None
    pages = 0
    reached_start = False
    while pages < max_pages:
        page = rpc.get_signatures(mint, limit=1000, before=before)
        pages += 1
        if not page:
            reached_start = True
            break
        sigs.extend(page)
        before = page[-1].get("signature")
        if len(page) < 1000:
            reached_start = True
            break
    info: dict[str, Any] = {"pages": pages, "signatures": len(sigs), "transactions": 0, "abgebrochen": not reached_start}
    if not reached_start:
        return [], info
    times = [s["blockTime"] for s in sigs if s.get("blockTime") is not None]
    if not times:
        return [], info
    t0 = min(times)
    wanted = [s["signature"] for s in sigs if s.get("err") is None and s.get("blockTime") is not None and s["blockTime"] <= t0 + seconds]
    info["transactions"] = len(wanted)
    trades: list[TradeEvent] = []
    for i in range(0, len(wanted), 100):
        chunk = wanted[i : i + 100]
        txs = rpc.get_transactions(chunk)
        for sig in chunk:
            parsed = parse_transaction(sig, txs.get(sig))
            if parsed is None or parsed.failed:
                continue
            for tr in parsed.trades:
                if tr.mint != mint or tr.virtual_token_reserves <= 0:
                    continue
                if not tr.timestamp and parsed.block_time:
                    tr.timestamp = int(parsed.block_time)
                if not tr.slot and parsed.slot:
                    tr.slot = int(parsed.slot)
                trades.append(tr)
    return ticks_from_trades(trades), info


# --- Aufbau ----------------------------------------------------------------------------------------------------------


def _hour(t: float) -> int:
    return int(t // 3600)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _diff_bootstrap(rows: list[tuple[float, bool, int]], n_boot: int = 1000, seed: int = 20261002) -> dict[str, float] | None:
    """Differenz der mittleren Rendite (bestanden − nicht bestanden); Rechenweg in replay.diff_bootstrap."""
    from .replay import diff_bootstrap

    return diff_bootstrap(rows, n_boot=n_boot, seed=seed)


def holdout_check(
    vectors: dict[str, dict[str, dict[str, Any]]],
    labels: dict[str, dict[str, Any]],
    *,
    split: float,
    quantile: float,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> dict[str, Any] | None:
    """Zeitsplit: Profil aus der früheren Hälfte, Ähnlichkeit auf der späteren Hälfte gegen das Label prüfen."""
    from .replay import wilson

    labelled = [m for m in labels if m in vectors and labels[m].get("gut") is not None]
    labelled.sort(key=lambda m: float(labels[m].get("t0") or 0))
    k = int(len(labelled) * split)
    train, test = labelled[:k], labelled[k:]
    if sum(1 for m in train if labels[m]["gut"]) < MIN_GOOD or len(test) < 5:
        return None
    prof = profile_from_vectors({m: vectors[m] for m in train if labels[m]["gut"]}, {m: vectors[m] for m in train if not labels[m]["gut"]}, quantile=quantile)
    cps = profile_checkpoints(prof)
    if not cps:
        return None
    cp = max(cps)
    rows: list[tuple[str, float, bool, float | None, int]] = []
    for m in test:
        vec = vectors[m].get(cp_key(cp))
        if vec is None:
            continue
        sim = similarity(prof, vec, cp)
        if sim is None:
            continue
        rows.append((m, sim["aehnlich"], bool(labels[m]["gut"]), labels[m].get("r_cons"), _hour(float(labels[m].get("t0") or 0))))
    if len(rows) < 5:
        return None
    passed = [r for r in rows if r[1] >= min_similarity]
    failed = [r for r in rows if r[1] < min_similarity]

    def group(rs: list[tuple[str, float, bool, float | None, int]]) -> dict[str, Any]:
        hits = sum(1 for r in rs if r[2])
        rets = [r[3] for r in rs if r[3] is not None]
        return {"n": len(rs), "treffer": hits, "wilson": wilson(hits, len(rs)) if rs else None, "mean_r": _mean(rets)}

    boot = _diff_bootstrap([(r[3], r[1] >= min_similarity, r[4]) for r in rows if r[3] is not None])
    return {
        "checkpoint": cp,
        "schwelle": min_similarity,
        "n_train": len(train),
        "n_test": len(rows),
        "bestanden": group(passed),
        "nicht_bestanden": group(failed),
        "bootstrap": boot,
    }


def _format_check(check: dict[str, Any]) -> str:
    def grp(name: str, g: dict[str, Any]) -> str:
        if not g["n"]:
            return f"  {name}: 0 Coins"
        w = g["wilson"]
        ci = f" (Wilson {w[0] * 100:.0f}–{w[1] * 100:.0f} %)" if w else ""
        r = f", Ø Netto-Rendite {g['mean_r'] * 100:+.1f} %" if g.get("mean_r") is not None else ""
        return f"  {name}: {g['n']} Coins, Treffer {g['treffer'] / g['n'] * 100:.0f} %{ci}{r}"

    lines = [f"Prüfung (Zeitsplit): Profil aus den ersten {check['n_train']} Coins, getestet an den späteren {check['n_test']} am Checkpoint {check['checkpoint']:g} s, Schwelle {check['schwelle']:.2f}"]
    lines.append(grp("Ähnlichkeit ≥ Schwelle", check["bestanden"]))
    lines.append(grp("Ähnlichkeit < Schwelle", check["nicht_bestanden"]))
    b = check.get("bootstrap")
    if b:
        verdict = "trennt" if b["lo"] > 0 else ("trennt NICHT (Intervall schließt 0 ein)" if b["hi"] >= 0 >= b["lo"] else "trennt in die falsche Richtung")
        lines.append(f"  Differenz der mittleren Rendite {b['diff'] * 100:+.1f} % (95 %-Block-Bootstrap {b['lo'] * 100:+.1f} … {b['hi'] * 100:+.1f} %, {b['blocks']} Stunden): {verdict}")
    elif not check["bestanden"]["n"] or not check["nicht_bestanden"]["n"]:
        lines.append("  alle Test-Coins liegen auf einer Seite der Schwelle: die Ähnlichkeit trennt hier nichts (Bänder zu weit oder Coins zu gleich)")
    else:
        lines.append("  zu wenige Stunden oder Renditen für ein Bootstrap-Intervall")
    return "\n".join(lines)


def build_profile(
    *,
    tape_path: str | None = None,
    records_path: str | None = None,
    paper_path: str | None = None,
    mints: list[tuple[str, bool | None]] | None = None,
    rpc: Any = None,
    entry_age_s: float = DEFAULT_ENTRY_AGE_S,
    horizon_s: float = DEFAULT_HORIZON_S,
    size_sol: float = DEFAULT_SIZE_SOL,
    costs: Any = None,
    quantile: float = DEFAULT_QUANTILE,
    split: float = 0.0,
    max_mints: int = 20,
    max_pages: int = 10,
) -> tuple[dict[str, Any], str]:
    """Referenzprofil aus gespeicherten Coins. Returns (Profil, Bericht). Das Profil kann leer sein (keine Checkpoints)."""
    from .replay import Costs, load_jsonl, load_tape

    costs = costs or Costs()
    cps = checkpoints_before(entry_age_s)
    vectors: dict[str, dict[str, dict[str, Any]]] = {}
    labels: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    notes: list[str] = []

    def bump(key: str, n: int = 1) -> None:
        counts[key] = counts.get(key, 0) + n

    def add_vectors(mint: str, vecs: dict[str, dict[str, Any]]) -> None:
        if vecs:
            vectors.setdefault(mint, {}).update({k: v for k, v in vecs.items() if k in {cp_key(c) for c in cps}})

    def add_label(mint: str, label: dict[str, Any], source: str) -> None:
        if label.get("gut") is None:
            return
        if mint in labels and labels[mint]["quelle"] == "tape":
            return  # das einheitliche Tape-Label geht vor
        labels[mint] = {**label, "quelle": source}

    # 1. Tape: Vektoren aus den Trades, Label aus derselben Kurvenmathematik wie `tape report`
    if tape_path:
        tape = load_tape(tape_path)
        bump("tape_coins", len(tape))
        for mint, rows in tape.items():
            dev = next((r.get("dev") for r in rows if r.get("dev")), None)
            add_vectors(mint, vectors_at_checkpoints(ticks_from_rows(rows), dev, cps))
            lab = label_from_rows(rows, entry_age_s, horizon_s, size_sol, costs)
            if lab.get("zensiert"):
                bump("tape_zensiert")
            elif not lab.get("handelbar"):
                bump("tape_nicht_handelbar")
            else:
                add_label(mint, lab, "tape")
    # 2. Records: Vektoren, die der Live-Modus zum Alarm gespeichert hat (Label kommt aus Tape oder Papier)
    if records_path:
        n = 0
        for rec in load_jsonl(records_path):
            prof = rec.get("profil") or {}
            if rec.get("mint") and isinstance(prof.get("vektoren"), dict) and prof["vektoren"]:
                add_vectors(rec["mint"], prof["vektoren"])
                n += 1
        bump("records_mit_vektor", n)
    # 3. Papier: Vektoren aus dem Kaufkontext, Label aus dem abgeschlossenen Papier-Ergebnis (mittleres PnL > 0)
    if paper_path:
        from .paper import _trades_from_records, load_paper

        trades = _trades_from_records(load_paper(paper_path))
        per_mint: dict[str, list[float]] = {}
        for tr in trades:
            per_mint.setdefault(tr["mint"], []).append(float(tr.get("pnl_pct") or 0.0))
            prof = (tr.get("kontext") or {}).get("profil") or {}
            if isinstance(prof.get("vektoren"), dict):
                add_vectors(tr["mint"], prof["vektoren"])
        bump("papier_coins", len(per_mint))
        for mint, pnls in per_mint.items():
            t0 = min((v.get("t0") for v in vectors.get(mint, {}).values() if v.get("t0")), default=None)
            add_label(mint, {"gut": sum(pnls) / len(pnls) > 0, "t0": t0, "pnl_pct": round(sum(pnls) / len(pnls), 2)}, "papier")
    # 4. Mint-Liste per RPC (begrenzt): Historie laden, Vektoren rechnen, Label aus der Datei oder aus der Historie
    if mints:
        if rpc is None:
            raise ValueError("--mints braucht einen RPC (--rpc)")
        todo = mints[:max_mints]
        if len(mints) > max_mints:
            notes.append(f"{len(mints) - max_mints} Mints wegen --max-mints {max_mints} nicht geladen")
        window = entry_age_s + horizon_s + CENSOR_SLACK_S
        for mint, given in todo:
            try:
                ticks, info = fetch_ticks(rpc, mint, window, max_pages=max_pages)
            except Exception as exc:  # noqa: BLE001 - ein Mint darf den Aufbau nicht beenden
                bump("mints_fehler")
                notes.append(f"{mint[:8]}…: Historie nicht ladbar ({exc})")
                continue
            if info.get("abgebrochen"):
                bump("mints_zu_gross")
                notes.append(f"{mint[:8]}…: mehr als {max_pages * 1000} Signaturen, Anfang nicht erreicht (--max-pages)")
                continue
            if not ticks:
                bump("mints_leer")
                continue
            bump("mints_geladen")
            add_vectors(mint, vectors_at_checkpoints(ticks, None, cps))
            if given is not None:
                add_label(mint, {"gut": given, "t0": ticks[0].ts}, "mints")
            else:
                lab = label_from_rows(rows_from_ticks(mint, ticks), entry_age_s, horizon_s, size_sol, costs)
                if lab.get("handelbar"):
                    add_label(mint, lab, "mints")
                else:
                    bump("mints_ohne_label")

    good = {m: vectors[m] for m, lab in labels.items() if lab["gut"] and m in vectors}
    bad = {m: vectors[m] for m, lab in labels.items() if not lab["gut"] and m in vectors}
    bump("ohne_vektor", sum(1 for m in labels if m not in vectors))
    sources = {k: v for k, v in counts.items() if v}
    rule = label_rule_text(entry_age_s, horizon_s, size_sol, costs)
    profile = profile_from_vectors(good, bad, quantile=quantile, label_rule=rule, sources=sources, checkpoints=cps)
    check = holdout_check(vectors, labels, split=split, quantile=quantile) if split and 0 < split < 1 else None
    if check:
        profile["pruefung"] = check

    lines = [f"Gespeicherte Coins: {len(labels)} mit Label ({len(good)} gut, {len(bad)} schlecht), {len(vectors)} mit Frühvektor"]
    if sources:
        lines.append("Quellen: " + ", ".join(f"{k} {v}" for k, v in sorted(sources.items())))
    lines.append(f"Label: {rule}")
    lines.append(f"Checkpoints (vor dem Einstieg, kein Look-ahead): {', '.join(cp_key(c) + ' s' for c in cps)}")
    by_source: dict[str, int] = {}
    for lab in labels.values():
        by_source[lab["quelle"]] = by_source.get(lab["quelle"], 0) + 1
    if by_source:
        lines.append("Label-Herkunft: " + ", ".join(f"{k} {v}" for k, v in sorted(by_source.items())))
    lines.extend(notes)
    if not profile_usable(profile):
        lines.append(f"Kein Profil: mindestens {MIN_GOOD} gute Coins mit Vektor je Checkpoint nötig (jetzt {len(good)}). Weiter aufzeichnen (live --tape --tape-sample 0.1) oder Mints mit Label angeben.")
    else:
        lines.append("")
        lines.append(describe_profile(profile))
        if not check:
            lines.append("Keine Zeitsplit-Prüfung (zu wenige Coins oder --split 0): ob die Ähnlichkeit Rendite trennt, ist damit ungeprüft.")
    return profile, "\n".join(lines)


def profile_suffix(prof: dict[str, Any] | None, has_profile: bool) -> str | None:
    """Kurztext für die Kopfzeile der Nachricht: Halter-Anstieg und Ähnlichkeit."""
    if not prof:
        return None
    parts = [f"Halter +{int(prof.get('anstieg') or 0)}/{int(prof.get('fenster_s') or RISE_WINDOW_S)}s"]
    sim = prof.get("aehnlich")
    if sim is not None:
        text = f"Profil {sim * 100:.0f} %"
        out = prof.get("ausserhalb") or []
        if out and sim < 1:
            text += f" ({', '.join(out[:3])})"
        parts.append(text)
    elif has_profile:
        parts.append("Profil ?")
    return " · ".join(parts)
