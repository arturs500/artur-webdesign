"""DexScreener-Bezahlsignale beobachten (Boosts, Enhanced Token Info = „Dex paid") und als Call-Quelle messen.

Was DexScreener verkauft (Quellen in docs/dexscreener_paid.md): Boost-Pakete heben für 12–24 h den Trending-Score
eines Tokens, ab 500 aktiven Boosts gibt es den „Golden Ticker"; Enhanced Token Info (Logo, Beschreibung, Socials,
299 USD laut Marktplatz-Snippet) ist das, was Trader „Dex paid" nennen. Beides ist öffentlich, mit Zeitstempel und
kostenlos abfragbar (api.dexscreener.com, ohne Schlüssel, 60 Anfragen je Minute für Profile/Boosts/Orders, 300 für
Paare/Preise). Ein bezahltes Signal zieht Aufmerksamkeit – ob der Follower daran verdient oder die Exit-Liquidität
liefert, ist die Hypothese von EXP004 (OQ-030). Dieses Modul misst sie, paper-only:

* ``DexWatcher`` fragt die Feeds ``/token-boosts/latest/v1`` und ``/token-profiles/latest/v1`` ab, schreibt jedes neue
  Ereignis (Boost-Kauf, neues Profil) als JSONL-Zeile und zieht Preis-Schnappschüsse bei +0, +5, +15 und +60 min
  (``/latest/dex/tokens/{mints}``, bis zu 30 Mints je Anfrage), innerhalb des Ratenbudgets.
* ``dex_report`` rechnet daraus die Netto-Rendite eines Followers je Horizont (Gebühr je Seite als Annahme), mit
  Wilson-Intervall und Block-Bootstrap nach Stunde, getrennt nach Ereignistyp und Boost-Größe, und verknüpft die
  Ereignisse mit den eigenen Alarm-Records (welche unserer Coins zahlten später, wie lange nach dem Launch).

Keine Käufe, keine Boosts, kein Schlüssel. Gegen die echte API konnte das Modul in der Arbeitsumgebung nicht
laufen (Host gesperrt); die Antwortformen folgen dem Spiegel der offiziellen Referenz (docs/dexscreener_paid.md) und
werden tolerant gelesen, Rohdaten bleiben in der Zeile.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

BASE_URL = "https://api.dexscreener.com"
FEED_BOOSTS = "/token-boosts/latest/v1"
FEED_PROFILES = "/token-profiles/latest/v1"
TOKENS = "/latest/dex/tokens/"
ORDERS = "/orders/v1/"
RATE_FEEDS_PER_MIN = 60  # token-profiles, token-boosts, orders (Referenz-Spiegel, direkt geprüft)
RATE_PAIRS_PER_MIN = 300  # pairs, tokens, search
MAX_TOKENS_PER_CALL = 30
DEFAULT_HORIZONS = (300.0, 900.0, 3600.0)
DEFAULT_FEE_BPS = 50  # je Seite: Annahme (Raydium 25 bps + Priority/Slippage); PumpSwap bis 125 bps, siehe Doku
BOOST_BUCKETS = ((0, 29, "10"), (30, 49, "30"), (50, 99, "50"), (100, 499, "100"), (500, 10**9, "500+"))

Fetch = Callable[[str], tuple[int, Any]]


def http_fetch(url: str, timeout: float = 8.0) -> tuple[int, Any]:
    """GET mit requests; Rückgabe (Status, JSON oder None). Netzfehler werden als Status 0 gemeldet."""
    import requests

    try:
        resp = requests.get(url, timeout=timeout, headers={"accept": "application/json", "user-agent": "holder-scorer dex beobachten"})
    except requests.RequestException:
        return 0, None
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def boost_bucket(amount: int | None) -> str:
    a = int(amount or 0)
    for lo, hi, name in BOOST_BUCKETS:
        if lo <= a <= hi:
            return name
    return "?"


def best_pair(pairs: Iterable[dict[str, Any]], mint: str, chain: str) -> dict[str, Any] | None:
    """Das liquideste Paar des Tokens auf der Kette (Token als Basis)."""
    best, best_liq = None, -1.0
    for p in pairs or ():
        if not isinstance(p, dict) or str(p.get("chainId") or "") != chain:
            continue
        base = (p.get("baseToken") or {}).get("address")
        if base != mint:
            continue
        liq = float(((p.get("liquidity") or {}).get("usd")) or 0.0)
        if liq > best_liq:
            best, best_liq = p, liq
    return best


def pairs_from(data: Any) -> list[dict[str, Any]]:
    """Paarliste aus einer ``/latest/dex/tokens``-Antwort (``{"pairs": [...]}`` oder nackte Liste), tolerant gelesen."""
    pairs = data.get("pairs") if isinstance(data, dict) else data
    return [p for p in (pairs or []) if isinstance(p, dict)]


def _num(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def snapshot_row(pair: dict[str, Any] | None, mint: str, now: float, event_id: str, after_s: float) -> dict[str, Any]:
    """Eine Preis-Zeile; ohne Paar bleibt sie leer (Token noch nicht indexiert oder ohne Liquidität)."""
    row: dict[str, Any] = {"typ": "preis", "t": round(now, 3), "mint": mint, "ereignis": event_id, "nach_s": after_s}
    if pair is None:
        row["fehlt"] = True
        return row
    txns = pair.get("txns") or {}
    m5 = txns.get("m5") or {}
    row.update(
        {
            "paar": pair.get("pairAddress"),
            "dex": pair.get("dexId"),
            "preis_usd": _num(pair.get("priceUsd")),
            "preis_native": _num(pair.get("priceNative")),
            "liq_usd": _num((pair.get("liquidity") or {}).get("usd")),
            "mcap": _num(pair.get("marketCap")),
            "fdv": _num(pair.get("fdv")),
            "vol_m5": _num((pair.get("volume") or {}).get("m5")),
            "vol_h1": _num((pair.get("volume") or {}).get("h1")),
            "vol_h24": _num((pair.get("volume") or {}).get("h24")),
            "kaeufe_m5": m5.get("buys"),
            "verkaeufe_m5": m5.get("sells"),
            "boosts_aktiv": (pair.get("boosts") or {}).get("active"),
            "paar_seit": pair.get("pairCreatedAt"),
        }
    )
    return row


@dataclass
class _Due:
    at: float
    mint: str
    event_id: str
    after_s: float


@dataclass
class DexWatcher:
    """Record-only: Feeds abfragen, Ereignisse und Preis-Schnappschüsse als JSONL schreiben. Kein Kauf, kein Boost."""

    out_path: str
    fetch: Fetch = http_fetch
    chain: str = "solana"
    poll_s: float = 60.0
    horizons: tuple[float, ...] = DEFAULT_HORIZONS
    feeds_per_min: int = RATE_FEEDS_PER_MIN - 10  # Reserve unter dem Limit
    pairs_per_min: int = RATE_PAIRS_PER_MIN - 50
    base_url: str = BASE_URL
    seen_boosts: set[tuple[str, int]] = field(default_factory=set)  # (mint, totalAmount)
    seen_profiles: set[str] = field(default_factory=set)
    due: list[_Due] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=lambda: {"anfragen": 0, "boosts": 0, "profile": 0, "preise": 0, "fehlend": 0, "limit": 0, "fehler": 0, "budget_wartet": 0})
    _last_poll: float = 0.0
    _minute: int = -1
    _used_feeds: int = 0
    _used_pairs: int = 0
    _cooldown_until: float = 0.0

    # --- Budget ------------------------------------------------------------------------------------------------
    def _budget(self, now: float, group: str) -> bool:
        minute = int(now // 60)
        if minute != self._minute:
            self._minute, self._used_feeds, self._used_pairs = minute, 0, 0
        if now < self._cooldown_until:
            return False
        if group == "feeds":
            if self._used_feeds >= self.feeds_per_min:
                self.stats["budget_wartet"] += 1
                return False
            self._used_feeds += 1
        else:
            if self._used_pairs >= self.pairs_per_min:
                self.stats["budget_wartet"] += 1
                return False
            self._used_pairs += 1
        return True

    def _get(self, path: str, now: float, group: str) -> Any:
        if not self._budget(now, group):
            return None
        self.stats["anfragen"] += 1
        status, data = self.fetch(self.base_url + path)
        if status == 429:
            self.stats["limit"] += 1
            self._cooldown_until = now + 60.0  # eine Minute Pause, dann weiter
            return None
        if status != 200:
            self.stats["fehler"] += 1
            return None
        return data

    def _write(self, row: dict[str, Any]) -> None:
        with open(self.out_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    # --- Feeds -------------------------------------------------------------------------------------------------
    def _event(self, kind: str, item: dict[str, Any], now: float) -> None:
        mint = str(item.get("tokenAddress") or "")
        event_id = f"{kind}:{mint}:{int(now)}"
        links = item.get("links") or []
        row = {
            "typ": kind,
            "t": round(now, 3),
            "kette": item.get("chainId"),
            "mint": mint,
            "url": item.get("url"),
            "amount": item.get("amount"),
            "totalAmount": item.get("totalAmount"),
            "paket": boost_bucket(item.get("amount")) if kind == "boost" else None,
            "links": len(links) if isinstance(links, list) else None,
            "beschreibung_len": len(str(item.get("description") or "")),
            "ereignis": event_id,
            "roh": item,
        }
        self._write(row)
        self.stats["boosts" if kind == "boost" else "profile"] += 1
        self.due.append(_Due(now, mint, event_id, 0.0))
        for h in self.horizons:
            self.due.append(_Due(now + h, mint, event_id, float(h)))

    def poll_feeds(self, now: float) -> None:
        boosts = self._get(FEED_BOOSTS, now, "feeds")
        for item in boosts if isinstance(boosts, list) else []:
            if not isinstance(item, dict) or str(item.get("chainId") or "") != self.chain:
                continue
            key = (str(item.get("tokenAddress") or ""), int(item.get("totalAmount") or 0))
            if key[0] and key not in self.seen_boosts:
                self.seen_boosts.add(key)
                self._event("boost", item, now)
        profiles = self._get(FEED_PROFILES, now, "feeds")
        for item in profiles if isinstance(profiles, list) else []:
            if not isinstance(item, dict) or str(item.get("chainId") or "") != self.chain:
                continue
            mint = str(item.get("tokenAddress") or "")
            if mint and mint not in self.seen_profiles:
                self.seen_profiles.add(mint)
                self._event("profil", item, now)
        if len(self.seen_boosts) > 50_000:
            self.seen_boosts = set(list(self.seen_boosts)[-20_000:])
        if len(self.seen_profiles) > 50_000:
            self.seen_profiles = set(list(self.seen_profiles)[-20_000:])

    # --- Preise ------------------------------------------------------------------------------------------------
    def take_snapshots(self, now: float) -> None:
        ready = [d for d in self.due if d.at <= now]
        if not ready:
            return
        ready.sort(key=lambda d: d.at)
        batch = ready[:MAX_TOKENS_PER_CALL]
        mints = sorted({d.mint for d in batch})
        data = self._get(TOKENS + ",".join(mints), now, "pairs")
        if data is None:
            return  # Budget oder Fehler: beim nächsten Tick erneut
        pairs = pairs_from(data)
        for d in batch:
            pair = best_pair(pairs, d.mint, self.chain)
            row = snapshot_row(pair, d.mint, now, d.event_id, d.after_s)
            row["geplant_nach_s"] = d.after_s
            row["verzug_s"] = round(now - d.at, 1)
            self._write(row)
            self.stats["preise"] += 1
            if pair is None:
                self.stats["fehlend"] += 1
        done = {id(d) for d in batch}
        self.due = [d for d in self.due if id(d) not in done]

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        if now - self._last_poll >= self.poll_s:
            self._last_poll = now
            self.poll_feeds(now)
        self.take_snapshots(now)

    def status_line(self) -> str:
        s = self.stats
        return (
            f"DexScreener: {s['anfragen']} Anfragen, {s['boosts']} Boost-Käufe, {s['profile']} neue Profile, {s['preise']} Preis-Schnappschüsse "
            f"({s['fehlend']} ohne Paar), 429: {s['limit']}, Fehler: {s['fehler']}, offene Schnappschüsse: {len(self.due)}"
        )

    def run(self, duration_s: float | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        start = time.time()
        try:
            while duration_s is None or time.time() - start < duration_s:
                self.tick()
                sleep(5.0)
        except KeyboardInterrupt:
            pass


# --- Auswertung -----------------------------------------------------------------------------------------------------


def load_rows(path: str) -> list[dict[str, Any]]:
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


def follower_return(p0: float | None, p1: float | None, fee_bps: int) -> float | None:
    """Netto-Multiplikator minus 1: Kauf bei p0, Verkauf bei p1, Gebühr je Seite (Preisimpact nicht modelliert)."""
    if not p0 or not p1 or p0 <= 0:
        return None
    f = 1.0 - fee_bps / 10_000
    return f * f * (p1 / p0) - 1.0


def dex_report(path: str, records_path: str | None = None, fee_bps: int = DEFAULT_FEE_BPS, horizons: Iterable[float] = DEFAULT_HORIZONS) -> tuple[str, dict[str, Any]]:
    from .replay import block_bootstrap, wilson

    rows = load_rows(path)
    events = {r["ereignis"]: r for r in rows if r.get("typ") in ("boost", "profil") and r.get("ereignis")}
    prices: dict[str, dict[float, dict[str, Any]]] = {}
    for r in rows:
        if r.get("typ") == "preis" and r.get("ereignis"):
            prices.setdefault(r["ereignis"], {})[float(r.get("geplant_nach_s", r.get("nach_s", 0)))] = r
    horizons = tuple(float(h) for h in horizons)
    groups: dict[str, dict[float, list[tuple[float, int]]]] = {}
    missing = 0
    for eid, ev in events.items():
        snaps = prices.get(eid, {})
        p0 = (snaps.get(0.0) or {}).get("preis_usd")
        if not p0:
            missing += 1
            continue
        keys = ["alle", "typ=" + str(ev.get("typ"))]
        if ev.get("typ") == "boost":
            keys.append("boost=" + str(ev.get("paket")))
        block = int(float(ev.get("t") or 0) // 3600)
        for h in horizons:
            p1 = (snaps.get(h) or {}).get("preis_usd")
            r = follower_return(p0, p1, fee_bps)
            if r is None:
                continue
            for k in keys:
                groups.setdefault(k, {}).setdefault(h, []).append((r, block))

    summary: dict[str, dict[str, Any]] = {}
    for k, by_h in groups.items():
        for h, vals in by_h.items():
            rs = [r for r, _ in vals]
            hits = sum(1 for r in rs if r > 0)
            summary[f"{k}|{h:g}"] = {
                "gruppe": k,
                "horizont_s": h,
                "n": len(rs),
                "treffer": hits / len(rs),
                "wilson": wilson(hits, len(rs)),
                "mean": sum(rs) / len(rs),
                "median": statistics.median(rs),
                "boot": block_bootstrap(rs, [b for _, b in vals]),
            }

    joined: dict[str, Any] | None = None
    if records_path:
        from .replay import load_jsonl

        launches: dict[str, float] = {}
        for rec in load_jsonl(records_path):
            if rec.get("mint") and rec.get("launch_received_at") is not None and "tier" in rec:
                launches.setdefault(rec["mint"], float(rec["launch_received_at"]))
        hits_list = [(ev["mint"], float(ev["t"]) - launches[ev["mint"]], ev.get("typ")) for ev in events.values() if ev.get("mint") in launches]
        joined = {
            "alarm_coins": len(launches),
            "davon_mit_bezahlsignal": len({m for m, _, _ in hits_list}),
            "median_minuten_nach_launch": round(statistics.median(d for _, d, _ in hits_list) / 60, 1) if hits_list else None,
            "boosts": sum(1 for _, _, t in hits_list if t == "boost"),
            "profile": sum(1 for _, _, t in hits_list if t == "profil"),
        }

    report = {"ereignisse": len(events), "ohne_startpreis": missing, "fee_bps": fee_bps, "horizonte": list(horizons), "summary": summary, "records": joined}
    return format_dex_report(report), report


def format_dex_report(report: dict[str, Any]) -> str:
    def pct(x: float | None) -> str:
        return "–" if x is None else f"{x * 100:+.1f} %"

    lines = [
        f"DexScreener-Bezahlsignale als Call-Quelle (EXP004-Kandidat, OQ-030): {report['ereignisse']} Ereignisse, {report['ohne_startpreis']} ohne Startpreis. "
        f"Follower-Rendite netto bei Gebühr {report['fee_bps']} bps je Seite (Annahme, ohne Preisimpact), Kauf beim Ereignis, Verkauf nach H Sekunden.",
        f"{'Gruppe':<14}{'H s':>6}{'n':>5}{'Treffer':>9}{'Wilson 95 %':>18}{'Ø netto':>10}{'Bootstrap 95 %':>22}{'Median':>9}",
    ]
    for key in sorted(report["summary"], key=lambda k: (report["summary"][k]["gruppe"] != "alle", report["summary"][k]["gruppe"], report["summary"][k]["horizont_s"])):
        s = report["summary"][key]
        w = s["wilson"]
        wil = "–" if w is None else f"[{w[0] * 100:.0f} %, {w[1] * 100:.0f} %]"
        b = s["boot"]
        ci = "–" if b is None else f"[{b['lo'] * 100:+.1f} %, {b['hi'] * 100:+.1f} %]"
        lines.append(f"{s['gruppe']:<14}{s['horizont_s']:>6.0f}{s['n']:>5}{s['treffer'] * 100:>8.0f} %{wil:>18}{pct(s['mean']):>10}{ci:>22}{pct(s['median']):>9}")
    if not report["summary"]:
        lines.append("(noch keine Ereignisse mit Start- und Folgepreis)")
    j = report.get("records")
    if j:
        lines.append(
            f"Eigene Alarm-Coins: {j['alarm_coins']}, davon später mit Bezahlsignal {j['davon_mit_bezahlsignal']} "
            f"({j['boosts']} Boosts, {j['profile']} Profile), Median {j['median_minuten_nach_launch']} min nach dem Launch."
        )
    lines.append(
        "Lesart: Erst ein Bootstrap-Intervall vollständig über 0 bei mindestens 200 Ereignissen aus mindestens 30 Stunden wäre ein Hinweis auf Edge; "
        "ein Intervall unter 0 heißt, der Follower ist die Exit-Liquidität. Kontrollgruppe (nicht bezahlte Token gleicher Größe) ist offen (OQ-030)."
    )
    return "\n".join(lines)
