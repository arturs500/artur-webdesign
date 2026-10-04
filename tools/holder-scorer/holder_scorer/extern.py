"""Außenquellen (0.3.6, OQ-033): Informationen nicht nur aus dem eigenen Papier-Test.

Bis 0.3.5 stammte alles Wissen des Sniper aus dem eigenen Datenstrom: Referenz-Coins aus Tape/Records/Papier, Labels
aus der Kurvenmathematik der ersten 300 s, Nachkontrolle nur per RPC. Drei kostenlose, schlüssellose Quellen von
außen schließen die blinden Flecken – record-only (R2), ohne neue RPC-Aufrufe im Live-Betrieb (R5):

* **Graduierungen** aus dem PumpPortal-Migrationsfeed (``subscribeMigration`` auf derselben WebSocket-Verbindung wie
  die Launches): jede Graduation der Plattform in Echtzeit, auch von Coins, die der Sniper nie gerufen hat. Das sind
  exakte externe Labels (``tape report --extern``) und Referenz-Coins für das Profil (``profil bauen --extern``).
  Beleg [Snippet] pumpportal.fun/data-api/real-time, abgerufen 2026-10-04 („fires when a token migrates from the
  bonding curve to an AMM pool", kostenlos); die Feldnamen des Ereignisses sind NICHT VERIFIZIERT, darum bleibt die
  Nachricht als ``roh`` in der Zeile.
* **Nachlauf** der eigenen Alarm- und Kontroll-Coins nach 1 h und 24 h über DexScreener ``/latest/dex/tokens``
  (bis 30 Mints je Anfrage, 300 je Minute, kein Schlüssel; docs/dexscreener_paid.md [Snippet]): lebt der Coin noch
  (Paar mit Liquidität), auf welcher DEX (``pumpswap``/``raydium`` statt ``pumpfun`` heißt graduiert), welche MC.
* **Risiko-Zweitmeinung** von Rugcheck (``/v1/tokens/{mint}/report/summary``, lesen kostenlos, kein Schlüssel laut
  Drittanleitungen [Snippet], Limits NICHT VERIFIZIERT): ein externer Score je GO/GESPERRT zum Alarmzeitpunkt,
  opt-in (``--rugcheck``), damit ``tape report`` prüfen kann, ob er über das Fair-Gate hinaus trennt.

Alles landet in einer eigenen Protokolldatei (``live --extern DATEI``), getrennt von Records und Tape. Nichts davon
beeinflusst BLICK/GO: erst messen, dann filtern (docs/experte.md R2, R4).
"""
from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .dexpaid import BASE_URL, MAX_TOKENS_PER_CALL, RATE_PAIRS_PER_MIN, TOKENS, best_pair, http_fetch, pairs_from, snapshot_row

Fetch = Callable[[str], tuple[int, Any]]

TIER_RANK = {"GO": 5, "GESPERRT": 4, "WIDERRUF": 3, "RUG": 2, "BLICK": 1}  # gemeinsame Rangfolge für Alarm-Gedächtnis und Nachlauf-Gruppen
GRUPPE_KONTROLLE = "KONTROLLE"
LAUNCH_TX_TYPES = {"create", "buy", "sell"}  # alles andere mit Mint auf dem Migrationsfeed gilt als Graduation
# Rugcheck-Kurzbericht: Felder score / score_normalised (0–100, höher = riskanter) / risks[] laut Drittanleitungen,
# abgerufen 2026-10-04 [Snippet]; Host in der Arbeitsumgebung gesperrt, Antwortform wird tolerant gelesen.
RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
PUMPFUN_DEX_IDS = {"pumpfun"}  # DexScreener-dexId der Bonding-Curve; jede andere DEX bedeutet: graduiert
UEBERLEBEN_LIQ_USD = 1000.0  # Annahme (OQ-033): darunter ist ein Paar nach einem Tag praktisch tot
# Graduation-Rate aller pump.fun-Launches laut Presse über Dune-Dashboards, abgerufen 2026-10-04 [Snippet]:
# 0,26 % (Mitte Juni 2026, dextools.io), 1,15 % Wochenhoch (bitget.com), ~1,4 % historisch (Dune via bitget.com).
GRADUATION_GRUNDRATE = (0.0026, 0.014)
FEED_REIFE_S = 86400.0  # ein Alarm ist erst beurteilbar, wenn der Feed danach noch so lange lief (Rechtszensur)
DEFAULT_NACHLAUF_HORIZONS = (3600.0, 86400.0)
RECENT_ALERTS_MAX = 5000


def _num(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def append_row(path: str, row: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")


def iter_rows(path: str) -> Iterable[dict[str, Any]]:
    if not path or not os.path.exists(path):
        return
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
                yield obj


# --- Migrationsfeed ---------------------------------------------------------------------------------------------------


def parse_migration(msg: dict[str, Any], now: float | None = None) -> dict[str, Any] | None:
    """Eine PumpPortal-Nachricht, die kein Launch und kein Trade ist, als Graduierungszeile; sonst None.

    Verlangt einen Mint und entweder ein ``txType`` außerhalb von create/buy/sell oder, ohne ``txType``, einen ``pool``
    außerhalb von ``pump`` (Launches ohne ``txType`` bleiben Launches: ``accept_launch`` behandelt fehlendes ``txType`` als
    create). Die Nachricht bleibt als ``roh`` erhalten, weil die Felder des Migrationsereignisses NICHT VERIFIZIERT sind.
    """
    mint = msg.get("mint")
    if not isinstance(mint, str) or len(mint) < 32:
        return None
    tx_type = msg.get("txType")
    pool = msg.get("pool")
    if isinstance(tx_type, str):
        if tx_type.lower() in LAUNCH_TX_TYPES:
            return None
    elif not (isinstance(pool, str) and pool and pool.lower() != "pump"):
        return None
    now = now if now is not None else time.time()
    return {
        "typ": "graduierung",
        "t": round(now, 3),
        "mint": mint,
        "signature": msg.get("signature"),
        "pool": msg.get("pool"),
        "txType": tx_type,
        "alarm": None,
        "roh": msg,
    }


def feed_row(ereignis: str, now: float | None = None) -> dict[str, Any]:
    return {"typ": "feed", "t": round(now if now is not None else time.time(), 3), "ereignis": ereignis}


# --- Rugcheck ---------------------------------------------------------------------------------------------------------


def rugcheck_fetch(mint: str, fetch: Fetch = http_fetch, now: float | None = None) -> dict[str, Any]:
    """Risikozeile für einen Mint. Liefert immer eine Zeile (bei Fehler mit ``fehlt``), nie eine Exception."""
    row: dict[str, Any] = {"typ": "risiko", "t": round(now if now is not None else time.time(), 3), "mint": mint, "quelle": "rugcheck", "alarm": None}
    try:
        status, data = fetch(RUGCHECK_URL.format(mint=mint))
    except Exception as exc:  # noqa: BLE001 - die Zeile muss geschrieben werden, der Fehler steht darin
        status, data = 0, {"fehler": repr(exc)}
    row["status"] = int(status or 0)
    if status != 200 or not isinstance(data, dict):
        row["fehlt"] = True
        if isinstance(data, dict) and data.get("fehler"):
            row["fehler"] = data["fehler"]
        return row
    row["score"] = _num(data.get("score"))
    row["score_norm"] = _num(data.get("score_normalised"))
    rugged = data.get("rugged")
    row["rugged"] = bool(rugged) if isinstance(rugged, bool) else None
    risks = data.get("risks")
    if isinstance(risks, list):
        row["risiken"] = [
            {"name": r.get("name"), "level": r.get("level"), "score": _num(r.get("score"))} for r in risks[:12] if isinstance(r, dict)
        ]
    if row["score"] is None and row["score_norm"] is None:
        row["roh"] = data  # Antwortform anders als erwartet: zur Verifikation aufheben (OQ-033)
    return row


# --- Protokoll lesen ----------------------------------------------------------------------------------------------------


@dataclass
class Extern:
    graduiert: dict[str, float] = field(default_factory=dict)  # Mint -> Zeit der ersten Graduierungszeile
    alarm_bei_graduierung: dict[str, str | None] = field(default_factory=dict)
    nachlauf: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    risiko: dict[str, dict[str, Any]] = field(default_factory=dict)
    feed: list[dict[str, Any]] = field(default_factory=list)
    zaehler: dict[str, int] = field(default_factory=dict)
    erster_t: float | None = None  # Feed-Zeilen (feed, graduierung): von wann bis wann der Migrationsfeed gelaufen ist
    letzter_t: float | None = None

    def dex_graduiert(self, mint: str) -> bool:
        """Graduation laut Nachlauf: ein Paar außerhalb der Bonding-Curve (laufzeitunabhängiger Marker)."""
        return any(r.get("dex") and str(r["dex"]).lower() not in PUMPFUN_DEX_IDS for r in self.nachlauf.get(mint, ()))

    def nachlauf_bekannt(self, mint: str) -> bool:
        return any(not r.get("fehlt") and r.get("dex") for r in self.nachlauf.get(mint, ()))

    def beurteilbar(self, t_ref: float) -> bool:
        """Lag der Alarm im Lauf des Feeds und lief der Feed danach noch mindestens FEED_REIFE_S?"""
        return self.erster_t is not None and self.letzter_t is not None and self.erster_t <= t_ref <= self.letzter_t - FEED_REIFE_S

    def luecken_s(self) -> float:
        """Summe der Trennungszeiten des Feeds (getrennt → verbunden)."""
        total, off_since = 0.0, None
        for row in sorted(self.feed, key=lambda r: float(r.get("t") or 0)):
            t = float(row.get("t") or 0)
            if row.get("ereignis") == "getrennt" and off_since is None:
                off_since = t
            elif row.get("ereignis") == "verbunden" and off_since is not None:
                total += max(0.0, t - off_since)
                off_since = None
        return round(total)


def load_extern(path: str) -> Extern:
    ex = Extern()
    for row in iter_rows(path):
        typ = str(row.get("typ") or "")
        ex.zaehler[typ] = ex.zaehler.get(typ, 0) + 1
        t = _num(row.get("t"))
        mint = row.get("mint")
        if typ == "graduierung" and mint:
            if mint not in ex.graduiert and t is not None:
                ex.graduiert[mint] = t
                ex.alarm_bei_graduierung[mint] = row.get("alarm")
        elif typ == "nachlauf" and mint:
            ex.nachlauf.setdefault(mint, []).append(row)
        elif typ == "risiko" and mint:
            ex.risiko.setdefault(mint, row)  # die erste Abfrage (zum Alarm) zählt
        elif typ == "feed":
            ex.feed.append(row)
        if typ in ("graduierung", "feed") and t is not None:
            ex.erster_t = t if ex.erster_t is None else min(ex.erster_t, t)
            ex.letzter_t = t if ex.letzter_t is None else max(ex.letzter_t, t)
    return ex


def describe_extern(ex: Extern, limit: int = 10) -> str:
    lines = ["Außenquellen: " + (", ".join(f"{k} {v}" for k, v in sorted(ex.zaehler.items())) or "leer")]
    if ex.erster_t is not None and ex.letzter_t is not None:
        lines.append(
            f"Migrationsfeed von {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ex.erster_t))} bis "
            f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(ex.letzter_t))} UTC, Trennungen {ex.luecken_s()} s, "
            f"{len(ex.graduiert)} Graduierungen, davon mit eigenem Alarm {sum(1 for a in ex.alarm_bei_graduierung.values() if a)}"
        )
    if ex.graduiert:
        lines.append("Letzte Graduierungen:")
        for mint, t in sorted(ex.graduiert.items(), key=lambda kv: -kv[1])[:limit]:
            alarm = ex.alarm_bei_graduierung.get(mint)
            lines.append(f"  {time.strftime('%H:%M:%S', time.gmtime(t))}  {mint}  {alarm or '–'}")
    if ex.risiko:
        with_score = sum(1 for r in ex.risiko.values() if r.get("score_norm") is not None)
        lines.append(f"Rugcheck: {len(ex.risiko)} Abfragen, {with_score} mit Score, {len(ex.risiko) - with_score} ohne (fehlt/Fehler)")
    if ex.nachlauf:
        rows = [r for rs in ex.nachlauf.values() for r in rs]
        lines.append(f"Nachlauf: {len(rows)} Zeilen für {len(ex.nachlauf)} Coins, ohne Paar {sum(1 for r in rows if r.get('fehlt'))}")
    return "\n".join(lines)


# --- Nachlauf -------------------------------------------------------------------------------------------------------------


def alert_groups(records_path: str) -> dict[str, tuple[str, float]]:
    """Je Mint der höchste Alarm (TIER_RANK) und die Zeit des ersten Alarms."""
    from .calibrate import load_records

    out: dict[str, tuple[str, float]] = {}
    for rec in load_records(records_path):
        tier = str(rec.get("tier") or "").upper()
        mint = rec.get("mint")
        t = _num(rec.get("alert_at") if rec.get("alert_at") is not None else rec.get("recorded_at"))
        if tier not in TIER_RANK or not mint or t is None:
            continue
        prev = out.get(mint)
        if prev is None:
            out[mint] = (tier, t)
        else:
            out[mint] = (tier if TIER_RANK[tier] > TIER_RANK[prev[0]] else prev[0], min(prev[1], t))
    return out


def control_groups(tape_path: str, exclude: Iterable[str] = ()) -> dict[str, tuple[str, float]]:
    """Kontroll-Mints aus dem Tape (erste Zeile mit ``control``), zeilenweise gelesen, ohne Alarm-Mints."""
    skip = set(exclude)
    out: dict[str, tuple[str, float]] = {}
    if not tape_path or not os.path.exists(tape_path):
        return out
    with open(tape_path, encoding="utf-8") as fh:
        for line in fh:
            if '"control":true' not in line and '"control": true' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            mint = row.get("mint") if isinstance(row, dict) else None
            if not mint or mint in skip or mint in out:
                continue
            t0 = _num(row.get("t0") if row.get("t0") is not None else row.get("seen_at"))
            if t0 is not None:
                out[mint] = (GRUPPE_KONTROLLE, t0)
    return out


def _done_keys(out_path: str) -> set[tuple[str, float]]:
    done: set[tuple[str, float]] = set()
    for row in iter_rows(out_path):
        if row.get("typ") == "nachlauf" and row.get("mint") and row.get("nach_s") is not None:
            done.add((str(row["mint"]), float(row["nach_s"])))
    return done


def nachlauf_fetch(
    records_path: str,
    out_path: str,
    *,
    tape_path: str | None = None,
    horizons: Iterable[float] = DEFAULT_NACHLAUF_HORIZONS,
    max_mints: int = 3000,
    per_min: int = RATE_PAIRS_PER_MIN - 50,
    fetch: Fetch = http_fetch,
    now: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    dry_run: bool = False,
    chain: str = "solana",
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Fällige Nachlauf-Schnappschüsse (Alarm- und Kontroll-Coins je Horizont) von DexScreener holen und anhängen.

    Idempotent: eine Zeile je (Mint, Horizont), auch ``fehlt`` zählt als erledigt. Alarme vor Kontrollen, ältester
    Fälligkeitstermin zuerst; ``max_mints`` begrenzt den Lauf, ``per_min`` das Tempo (300 Anfragen je Minute laut
    Referenz, Reserve abgezogen). Kein RPC.
    """
    now = now if now is not None else time.time()
    targets = alert_groups(records_path)
    if tape_path:
        targets.update(control_groups(tape_path, exclude=targets))
    done = _done_keys(out_path)
    due: list[tuple[int, float, str, str, float, float]] = []
    for mint, (gruppe, t_ref) in targets.items():
        for h in horizons:
            h = float(h)
            if now - t_ref >= h and (mint, h) not in done:
                due.append((1 if gruppe == GRUPPE_KONTROLLE else 0, t_ref + h, mint, gruppe, t_ref, h))
    due.sort()
    todo = due[:max_mints]
    stats: dict[str, Any] = {
        "ziele": len(targets),
        "faellig": len(due),
        "geplant": len(todo),
        "je_gruppe": {},
        "je_horizont": {},
        "anfragen": 0,
        "zeilen": 0,
        "fehlend": 0,
        "limit": 0,
        "fehler": 0,
    }
    for _, _, _, gruppe, _, h in todo:
        stats["je_gruppe"][gruppe] = stats["je_gruppe"].get(gruppe, 0) + 1
        stats["je_horizont"][str(int(h))] = stats["je_horizont"].get(str(int(h)), 0) + 1
    by_mint: dict[str, list[tuple[str, float, float]]] = {}
    for _, _, mint, gruppe, t_ref, h in todo:
        by_mint.setdefault(mint, []).append((gruppe, t_ref, h))
    stats["anfragen_geplant"] = -(-len(by_mint) // MAX_TOKENS_PER_CALL) if by_mint else 0
    if dry_run:
        return stats
    mints = list(by_mint)
    used = 0
    for i in range(0, len(mints), MAX_TOKENS_PER_CALL):
        if used >= per_min:
            sleep(60.0)
            used = 0
        chunk = mints[i : i + MAX_TOKENS_PER_CALL]
        status, data = fetch(base_url + TOKENS + ",".join(chunk))
        used += 1
        stats["anfragen"] += 1
        if status == 429:
            stats["limit"] += 1
            break  # Limit erreicht: der nächste Lauf holt den Rest
        if status != 200:
            stats["fehler"] += 1
            continue
        pairs = pairs_from(data)
        for mint in chunk:
            pair = best_pair(pairs, mint, chain)
            for gruppe, t_ref, h in by_mint[mint]:
                row = snapshot_row(pair, mint, now, gruppe, h)
                row.pop("ereignis", None)
                row.update({"typ": "nachlauf", "gruppe": gruppe, "t_ref": round(t_ref, 3), "nach_s": h, "alter_s": round(now - t_ref)})
                append_row(out_path, row)
                stats["zeilen"] += 1
                if pair is None:
                    stats["fehlend"] += 1
    return stats


def format_nachlauf_stats(stats: dict[str, Any], dry_run: bool = False) -> str:
    groups = ", ".join(f"{k} {v}" for k, v in sorted(stats["je_gruppe"].items())) or "–"
    hors = ", ".join(f"+{int(k) // 3600} h: {v}" for k, v in sorted(stats["je_horizont"].items(), key=lambda kv: int(kv[0]))) or "–"
    head = f"Nachlauf: {stats['ziele']} Coins, {stats['faellig']} fällige Schnappschüsse, {stats['geplant']} in diesem Lauf ({groups}; {hors})"
    if dry_run:
        return head + f"; Trockenlauf: {stats['anfragen_geplant']} DexScreener-Anfragen nötig, nichts geschrieben."
    return head + f"; {stats['anfragen']} Anfragen, {stats['zeilen']} Zeilen geschrieben ({stats['fehlend']} ohne Paar), 429: {stats['limit']}, Fehler: {stats['fehler']}."


# --- Auswertung für tape report ---------------------------------------------------------------------------------------------


def extern_summary(
    alerts: list[dict[str, Any]],
    controls: dict[str, float],
    outcomes: list[Any],
    ex: Extern,
    primary: tuple[str, float, float] = ("GO", 30.0, 300.0),
) -> dict[str, Any]:
    """Graduation von außen, Nachlauf-Überleben und Rugcheck-Trennung je Gruppe; nur einfache Dicts (JSON-fähig)."""
    from .replay import wilson

    groups: dict[str, dict[str, float]] = {}
    per_mint: dict[str, tuple[str, float]] = {}
    for rec in alerts:
        tier = str(rec.get("tier") or "").upper()
        mint = rec.get("mint")
        t = _num(rec.get("alert_at"))
        if tier not in TIER_RANK or not mint or t is None:
            continue
        prev = per_mint.get(mint)
        per_mint[mint] = (tier, t) if prev is None else (tier if TIER_RANK[tier] > TIER_RANK[prev[0]] else prev[0], min(prev[1], t))
    for mint, (tier, t) in per_mint.items():
        groups.setdefault(tier, {})[mint] = t
    for mint, t0 in controls.items():
        if mint not in per_mint:
            groups.setdefault(GRUPPE_KONTROLLE, {})[mint] = float(t0)

    tape_grad: dict[str, tuple[int, int]] = {}
    hit_by_mint: dict[str, bool] = {}
    for o in outcomes:
        if (o.latency_s, o.horizon_s) != (primary[1], primary[2]):
            continue
        k, n = tape_grad.get(o.tier, (0, 0))
        tape_grad[o.tier] = (k + (1 if o.graduated else 0), n + 1)
        if o.tier == primary[0]:
            hit_by_mint.setdefault(o.mint, o.r_cons > 0)

    graduation: dict[str, dict[str, Any]] = {}
    for gruppe, mints in groups.items():
        judge = [m for m, t in mints.items() if ex.beurteilbar(t) or ex.nachlauf_bekannt(m)]
        grad = sum(1 for m in judge if m in ex.graduiert or ex.dex_graduiert(m))
        k, n = tape_grad.get(gruppe, (0, 0))
        graduation[gruppe] = {
            "n": len(mints),
            "beurteilbar": len(judge),
            "offen": len(mints) - len(judge),
            "graduiert": grad,
            "anteil": (grad / len(judge)) if judge else None,
            "wilson": wilson(grad, len(judge)) if judge else None,
            "tape_anteil": (k / n) if n else None,
        }
    ctrl = graduation.get(GRUPPE_KONTROLLE)
    plausibel = None
    if ctrl and ctrl["anteil"] is not None and ctrl["beurteilbar"] >= 50:
        lo, hi = GRADUATION_GRUNDRATE
        plausibel = lo * 0.5 <= ctrl["anteil"] <= hi * 2

    nachlauf: dict[str, dict[str, Any]] = {}
    for gruppe, mints in groups.items():
        for mint in mints:
            for row in ex.nachlauf.get(mint, ()):  # die Gruppe im Report folgt den Records, nicht der Zeile
                h = _num(row.get("nach_s"))
                if h is None:
                    continue
                key = f"{gruppe}|{int(h)}"
                cell = nachlauf.setdefault(key, {"gruppe": gruppe, "nach_s": h, "n": 0, "verspaetet": 0, "ueberlebt": 0, "mcaps": []})
                if _num(row.get("alter_s")) is not None and float(row["alter_s"]) > 2 * h:
                    cell["verspaetet"] += 1
                    continue
                cell["n"] += 1
                liq = _num(row.get("liq_usd"))
                if not row.get("fehlt") and liq is not None and liq >= UEBERLEBEN_LIQ_USD:
                    cell["ueberlebt"] += 1
                    if _num(row.get("mcap")) is not None:
                        cell["mcaps"].append(float(row["mcap"]))
    for cell in nachlauf.values():
        cell["anteil"] = (cell["ueberlebt"] / cell["n"]) if cell["n"] else None
        cell["wilson"] = wilson(cell["ueberlebt"], cell["n"]) if cell["n"] else None
        cell["median_mcap"] = statistics.median(cell["mcaps"]) if cell["mcaps"] else None
        del cell["mcaps"]

    go_mints = list(groups.get(primary[0], {}))
    scored = [(ex.risiko[m].get("score_norm"), m) for m in go_mints if m in ex.risiko and ex.risiko[m].get("score_norm") is not None]
    risiko: dict[str, Any] = {"go": len(go_mints), "mit_score": len(scored), "abgefragt": sum(1 for m in go_mints if m in ex.risiko)}
    rated = [(s, m) for s, m in scored if m in hit_by_mint]
    if rated:
        med = statistics.median(s for s, _ in rated)
        low = [hit_by_mint[m] for s, m in rated if s <= med]
        high = [hit_by_mint[m] for s, m in rated if s > med]
        risiko.update(
            {
                "median_score": med,
                "niedrig": {"n": len(low), "treffer": sum(low), "wilson": wilson(sum(low), len(low)) if low else None},
                "hoch": {"n": len(high), "treffer": sum(high), "wilson": wilson(sum(high), len(high)) if high else None},
            }
        )
        if len(low) >= 20 and len(high) >= 20:
            lr = sum(low) / len(low)
            hr = sum(high) / len(high)
            risiko["lesart"] = "Rugcheck trennt (niedriges Risiko trifft öfter)" if lr > hr else "Rugcheck trennt nicht über das Fair-Gate hinaus"
        else:
            risiko["lesart"] = "zu wenig (mindestens 20 GO je Hälfte)"
    return {
        "feed": {"erster_t": ex.erster_t, "letzter_t": ex.letzter_t, "luecken_s": ex.luecken_s(), "graduierungen": len(ex.graduiert)},
        "graduation": graduation,
        "kontrollen_plausibel": plausibel,
        "grundrate": list(GRADUATION_GRUNDRATE),
        "nachlauf": nachlauf,
        "risiko": risiko,
    }


def extern_lines(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return []

    def wil(w: Any) -> str:
        return "–" if not w else f"[{w[0] * 100:.0f} %, {w[1] * 100:.0f} %]"

    def pct(x: float | None) -> str:
        return "–" if x is None else f"{x * 100:.1f} %"

    f = summary["feed"]
    lines = [
        f"Außenquellen (record-only, OQ-033): Migrationsfeed mit {f['graduierungen']} Graduierungen, Trennungen {f['luecken_s']} s; "
        f"beurteilbar sind Alarme bis {int(FEED_REIFE_S // 3600)} h vor dem Feed-Ende.",
    ]
    order = sorted(summary["graduation"], key=lambda g: -TIER_RANK.get(g, 0))
    for g in order:
        c = summary["graduation"][g]
        lines.append(
            f"  Graduation {g:<9} n = {c['n']:>4}, beurteilbar {c['beurteilbar']:>4}, offen {c['offen']:>4}: extern {pct(c['anteil']):>7} {wil(c['wilson'])}"
            + (f", im Tape-Fenster {pct(c['tape_anteil'])}" if c["tape_anteil"] is not None else "")
        )
    lo, hi = summary["grundrate"]
    plaus = summary["kontrollen_plausibel"]
    lines.append(
        f"  Grundrate aller Launches {lo * 100:.2f}–{hi * 100:.1f} % [Snippet, Presse über Dune 2026]; Kontroll-Stichprobe "
        + ("plausibel" if plaus else "außerhalb des Bereichs – Stichprobe prüfen" if plaus is False else "noch nicht prüfbar (unter 50 beurteilbare Kontrollen)")
        + "."
    )
    for key in sorted(summary["nachlauf"], key=lambda k: (-TIER_RANK.get(k.split("|")[0], 0), float(k.split("|")[1]))):
        c = summary["nachlauf"][key]
        mc = "–" if c["median_mcap"] is None else f"{c['median_mcap'] / 1000:.0f} k USD"
        lines.append(
            f"  Nachlauf {c['gruppe']:<9} +{int(c['nach_s']) // 3600:>3} h: n = {c['n']:>4} (verspätet {c['verspaetet']}), lebt (Liquidität ≥ {UEBERLEBEN_LIQ_USD:.0f} USD) "
            f"{pct(c['anteil']):>7} {wil(c['wilson'])}, Median-MC der Überlebenden {mc}"
        )
    r = summary["risiko"]
    if r.get("abgefragt"):
        text = f"  Rugcheck: {r['abgefragt']} von {r['go']} GO abgefragt, {r['mit_score']} mit Score"
        if "median_score" in r:
            text += (
                f"; Median {r['median_score']:.0f}: Treffer bei niedrigem Risiko {r['niedrig']['treffer']}/{r['niedrig']['n']} {wil(r['niedrig']['wilson'])}, "
                f"bei hohem {r['hoch']['treffer']}/{r['hoch']['n']} {wil(r['hoch']['wilson'])} → {r['lesart']}"
            )
        lines.append(text + ".")
    return lines
