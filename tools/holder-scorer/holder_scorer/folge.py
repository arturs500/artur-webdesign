"""Wallet-Folge (0.3.8, OQ-035): beobachtete Wallets, ihre Käufe als Alarm, eigene Funde, Auswertung.

Die Idee des Nutzers: Es gibt Wallets, die früh in Coins einsteigen, die später viral gehen. Kauft so ein Wallet,
soll der Bot das melden, mit dem Kontext (welches Wallet, wie oft es sonst traf, welches Narrativ, wo der Coin
steht), und aufzeichnen, was danach passiert, auch bis zum nächsten Tag. Entscheiden tut der Mensch.

Drei Teile, alle ohne zusätzliche RPC-Aufrufe:

* **Liste** (``parse_wallets_file``): eine Textdatei, Zeile ``<Adresse> [Tag] [k/n] # Notiz``. Adressen von Solscan
  oder DexScreener trägt der Nutzer von Hand ein (keine Solscan-API: Abo und Schlüssel, Eskalationsliste); ``wallets
  scout`` schreibt eigene Funde im selben Format dazu.
* **Scout** (``scout``): aus dem eigenen Tape (``live --tape --tape-sample``) die frühen Käufer je Coin, Label aus den
  Außenquellen (Graduation laut Migrationsfeed, Paar außerhalb der Kurve, Liquidität nach 24 h). Je Wallet
  Trefferquote mit Wilson-Intervall gegen die Kontrollgruppe. Die Stichprobe ist das Tape, also Alarm-Coins plus
  Kontroll-Anteil: Quoten gelten relativ zur Kontrollrate, nicht absolut.
* **Report** (``wallet_report``): je Wallet die FOLGE-Alarme und was aus den Coins wurde: Graduation, Überleben nach
  24 h, Vielfaches des Kurses nach 1 h und 24 h (DexScreener-Nachlauf gegen den Kurvenpreis beim Alarm).

Alles ist Aufzeichnung und Messung (R2 in docs/experte.md): kein Gate, kein Kauf, kein Einfluss auf BLICK oder GO.
"""
from __future__ import annotations

import hashlib
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .extern import DEFAULT_NACHLAUF_HORIZONS, UEBERLEBEN_LIQ_USD, Extern, iter_rows
from .pump import LAMPORTS_PER_SOL

B58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
RATIO = re.compile(r"^(\d+)/(\d+)$")
FEE_BPS = 125  # Kurvengebühr je Seite (1 % Protokoll + Creator-Fee), wie in docs/sniper_review.md 2.3


@dataclass
class WalletEntry:
    address: str
    tag: str = ""
    quelle: str = "import"  # import | scout
    notiz: str = ""
    treffer: int | None = None  # k: Coins, die gut ausgingen
    coins: int | None = None  # n: beurteilbare Coins, in denen das Wallet früh war

    @property
    def kurz(self) -> str:
        return self.address[:4] + "…" + self.address[-4:]

    @property
    def name(self) -> str:
        return self.tag or self.kurz

    def stats_text(self) -> str:
        if self.coins:
            return f"Treffer {self.treffer or 0}/{self.coins}"
        return "ohne Statistik"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_wallets_line(line: str) -> WalletEntry | None:
    """``<Adresse> [Tag …] [k/n] # Notiz``; Tag und Notiz frei, ``k/n`` aus dem Scout. Ungültige Adresse → None."""
    text, _, notiz = line.partition("#")
    parts = text.split()
    if not parts or not B58.match(parts[0]):
        return None
    entry = WalletEntry(address=parts[0], notiz=notiz.strip())
    words: list[str] = []
    for p in parts[1:]:
        m = RATIO.match(p)
        if m:
            entry.treffer, entry.coins = int(m.group(1)), int(m.group(2))
        else:
            words.append(p)
    if words and words[0].lower() == "scout":
        entry.quelle = "scout"
        words = words[1:]
    entry.tag = " ".join(words)
    return entry


def parse_wallets_file(path: str) -> dict[str, WalletEntry]:
    """Alle gültigen Zeilen; Duplikate: die spätere Zeile ergänzt, was die frühere nicht hatte. OSError reicht durch."""
    out: dict[str, WalletEntry] = {}
    bad = 0
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entry = parse_wallets_line(line)
            if entry is None:
                bad += 1
                continue
            prev = out.get(entry.address)
            if prev is None:
                out[entry.address] = entry
                continue
            prev.tag = entry.tag or prev.tag
            prev.notiz = entry.notiz or prev.notiz
            if entry.coins:
                prev.treffer, prev.coins, prev.quelle = entry.treffer, entry.coins, entry.quelle
    if bad:
        print(f"Wallet-Liste {path}: {bad} Zeile(n) ohne gültige Adresse übersprungen")
    return out


def wallets_file_hash(path: str) -> str:
    """Kurzer Hash der Datei, damit Aufzeichnungen sagen, mit welcher Liste sie entstanden sind (nicht im Regel-Hash)."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def format_wallet_line(e: WalletEntry) -> str:
    parts = [e.address]
    if e.quelle == "scout":
        parts.append("scout")
    if e.tag:
        parts.append(e.tag)
    if e.coins:
        parts.append(f"{e.treffer or 0}/{e.coins}")
    line = " ".join(parts)
    return line + (f"  # {e.notiz}" if e.notiz else "")


def folge_suffix(entry: WalletEntry | None, folge: dict[str, Any], after: str | None = None) -> str:
    """Kopfzeile des FOLGE-Alarms: wer kaufte, was das Wallet sonst traf, wie viel, und was der Bot nicht weiß."""
    name = entry.name if entry else str(folge.get("wallet", ""))[:8]
    parts = [f"Wallet {name}"]
    if entry is not None:
        parts.append(f"Quelle {entry.quelle}")
        parts.append(entry.stats_text())
    sol = folge.get("sol")
    if sol is not None:
        parts.append(f"Kauf {float(sol):.2f} SOL")
    if folge.get("bundle"):
        parts.append("im Create-Block")
    if folge.get("spaet"):
        parts.append("spät gesehen (Alter, Dev-Historie, Bundle unbekannt)")
    if after:
        parts.append(after)
    return " · ".join(parts)


# --- Scout: eigene Funde aus Tape und Außenquellen ---------------------------------------------------------------------


@dataclass
class ScoutResult:
    coins: int = 0  # getapete Coins
    beurteilbar: int = 0  # davon mit Label (Graduation oder Nachlauf am Horizont)
    kontrollen: int = 0  # beurteilbare Kontroll-Coins
    kontroll_rate: float | None = None
    kontroll_wilson: tuple[float, float] | None = None
    grundrate_alle: float | None = None
    wallets: int = 0  # Wallets mit mindestens einem frühen Kauf
    bots: int = 0  # ausgeschlossen: früh in mehr als max_anteil aller Coins
    kandidaten: list[dict[str, Any]] = field(default_factory=list)
    lesart: str = ""


def _good(ex: Extern, mint: str, horizon_s: float) -> bool | None:
    """True gut, False schlecht, None nicht beurteilbar: Graduation, Paar außerhalb der Kurve oder Liquidität am Horizont."""
    if mint in ex.graduiert or ex.dex_graduiert(mint):
        return True
    rows = [r for r in ex.nachlauf.get(mint, ()) if float(r.get("nach_s") or 0) >= horizon_s]
    if not rows:
        return None
    best = max(rows, key=lambda r: float(r.get("nach_s") or 0))
    if best.get("fehlt"):
        return None  # fehlt ist nicht tot: DexScreener-Abdeckung der Kurve ist ungeprüft (OQ-033 e)
    liq = best.get("liq_usd")
    return bool(liq is not None and float(liq) >= UEBERLEBEN_LIQ_USD)


def scout(
    tape_path: str,
    ex: Extern,
    *,
    frueh_s: float = 60.0,
    min_coins: int = 3,
    max_anteil: float = 0.2,
    horizon_s: float = DEFAULT_NACHLAUF_HORIZONS[-1],
    now: float | None = None,
) -> ScoutResult:
    """Frühe Käufer je getapetem Coin (ohne Dev, ohne Create-Block, innerhalb ``frueh_s`` nach t0), Label aus den
    Außenquellen, je Wallet Trefferquote mit Wilson-Intervall gegen die Kontrollgruppe."""
    from .replay import wilson

    coins: dict[str, dict[str, Any]] = {}
    for r in iter_rows(tape_path):
        mint = r.get("mint")
        if not mint or r.get("ts") is None:
            continue
        c = coins.setdefault(mint, {"t0": float(r.get("t0") or 0), "dev": r.get("dev"), "control": bool(r.get("control")), "rows": []})
        c["rows"].append(r)
    res = ScoutResult(coins=len(coins))
    if not coins:
        res.lesart = "Tape leer: `live --tape live_tape.jsonl --tape-sample 0.1` aufzeichnen"
        return res
    early: dict[str, dict[str, Any]] = {}  # wallet -> {coins: set, good: set, bad: set, first: t, last: t}
    labels: dict[str, bool | None] = {}
    for mint, c in coins.items():
        rows = c["rows"]
        first_slot = min(int(r.get("slot") or 0) for r in rows)
        label = _good(ex, mint, horizon_s)
        labels[mint] = label
        if label is not None:
            res.beurteilbar += 1
            if c["control"]:
                res.kontrollen += 1
        for r in rows:
            if not r.get("buy") or not r.get("user") or r.get("user") == c["dev"]:
                continue
            if int(r.get("slot") or 0) == first_slot or float(r["ts"]) - c["t0"] > frueh_s:
                continue
            w = early.setdefault(r["user"], {"coins": set(), "good": set(), "bad": set(), "first": float(r["ts"]), "last": float(r["ts"])})
            w["coins"].add(mint)
            w["first"], w["last"] = min(w["first"], float(r["ts"])), max(w["last"], float(r["ts"]))
            if label is True:
                w["good"].add(mint)
            elif label is False:
                w["bad"].add(mint)
    res.wallets = len(early)
    good_controls = sum(1 for m, c in coins.items() if c["control"] and labels[m] is True)
    if res.kontrollen:
        res.kontroll_rate = good_controls / res.kontrollen
        res.kontroll_wilson = wilson(good_controls, res.kontrollen)
    good_all = sum(1 for m in coins if labels[m] is True)
    if res.beurteilbar:
        res.grundrate_alle = good_all / res.beurteilbar
    # Vergleichswert: Wilson-Obergrenze der Kontrollen (ab 20 beurteilbaren), sonst die Grundrate aller getapeten Coins
    if res.kontroll_wilson is not None and res.kontrollen >= 20:
        bar, bar_text = res.kontroll_wilson[1], f"Kontrollgruppe {res.kontroll_rate:.1%} (n={res.kontrollen}, Wilson-Obergrenze {res.kontroll_wilson[1]:.1%})"
    elif res.grundrate_alle is not None:
        bar, bar_text = res.grundrate_alle, f"Grundrate aller getapeten Coins {res.grundrate_alle:.1%} (verzerrt: Alarm-Coins, keine Kontrollgruppe ab 20)"
    else:
        bar, bar_text = None, "keine Labels: Außenquellen (`quellen nachlauf`, Migrationsfeed) fehlen"
    for addr, w in early.items():
        n_total = len(w["coins"])
        if n_total / max(len(coins), 1) > max_anteil:
            res.bots += 1  # früh in jedem fünften Coin: Sniper- oder Bump-Bot, kein Narrativ-Käufer
            continue
        n = len(w["good"]) + len(w["bad"])
        k = len(w["good"])
        if n < min_coins:
            continue
        wi = wilson(k, n)
        if wi is None or bar is None or wi[0] <= bar:
            continue
        res.kandidaten.append(
            {
                "wallet": addr, "treffer": k, "coins": n, "frueh_in": n_total, "wilson": [round(wi[0], 4), round(wi[1], 4)],
                "seit": w["first"], "zuletzt": w["last"],
            }
        )
    res.kandidaten.sort(key=lambda c: (-c["wilson"][0], -c["coins"]))
    res.lesart = (
        f"{res.coins} Coins im Tape, {res.beurteilbar} beurteilbar, {res.wallets} Wallets früh dabei, {res.bots} als Bot ausgeschlossen; "
        f"Vergleich: {bar_text}; Kandidat = Wilson-Untergrenze über dem Vergleichswert bei mindestens {min_coins} beurteilbaren Coins"
    )
    return res


def scout_lines(res: ScoutResult, now: float | None = None) -> list[str]:
    """Zeilen im Listenformat, so dass ``wallets scout --out`` direkt als ``--wallets`` taugt."""
    now = now if now is not None else time.time()
    out = [f"# wallets scout {time.strftime('%Y-%m-%d %H:%M', time.gmtime(now))} UTC: {res.lesart}"]
    for c in res.kandidaten:
        seit = time.strftime("%Y-%m-%d", time.gmtime(c["seit"]))
        e = WalletEntry(
            c["wallet"], quelle="scout", treffer=c["treffer"], coins=c["coins"],
            notiz=f"Wilson {c['wilson'][0]:.0%}–{c['wilson'][1]:.0%}, früh in {c['frueh_in']} Coins, seit {seit}",
        )
        out.append(format_wallet_line(e))
    return out


# --- Report: was aus den FOLGE-Alarmen wurde --------------------------------------------------------------------------


def _curve_price_sol(curve: dict[str, Any] | None) -> float | None:
    """SOL je ganzem Token aus den virtuellen Reserven des Records (9 bzw. 6 Dezimalen), wie paper.curve_price."""
    if not curve:
        return None
    vq, vt = curve.get("virtual_quote_reserves"), curve.get("virtual_token_reserves")
    if not vq or not vt or float(vt) <= 0:
        return None
    return (float(vq) / LAMPORTS_PER_SOL) / (float(vt) / 1e6)


def _nachlauf_at(ex: Extern, mint: str, horizon_s: float) -> dict[str, Any] | None:
    rows = [r for r in ex.nachlauf.get(mint, ()) if abs(float(r.get("nach_s") or 0) - horizon_s) < 1.0]
    if not rows:
        return None
    row = rows[-1]
    alter = row.get("alter_s")
    if alter is not None and float(alter) > 2 * horizon_s:
        return None  # verspäteter Schnappschuss, wie in extern_summary
    return row


def wallet_report(
    records: Iterable[dict[str, Any]],
    ex: Extern,
    wallets: dict[str, WalletEntry] | None = None,
    *,
    horizons: tuple[float, ...] = DEFAULT_NACHLAUF_HORIZONS,
    fee_bps: int = FEE_BPS,
) -> dict[str, Any]:
    """Je Wallet: FOLGE-Alarme, Graduation, Überleben und Kurs-Vielfaches nach den Horizonten; nur einfache Dicts."""
    from .dexpaid import follower_return
    from .replay import wilson

    per: dict[str, dict[str, Any]] = {}
    for rec in records:
        if str(rec.get("tier") or "").upper() != "FOLGE":
            continue
        fo = rec.get("folge") or {}
        wallet, mint = fo.get("wallet"), rec.get("mint")
        if not wallet or not mint:
            continue
        w = per.setdefault(wallet, {"alarme": 0, "mints": {}, "spaet": 0})
        if mint in w["mints"]:
            continue  # ein Alarm je Coin und Wallet
        w["alarme"] += 1
        w["spaet"] += 1 if rec.get("spaet") else 0
        w["mints"][mint] = {"t": float(rec.get("alert_at") or 0), "p0": _curve_price_sol(rec.get("curve"))}
    out: dict[str, Any] = {"wallets": {}, "horizonte": list(horizons), "fee_bps": fee_bps}
    for wallet, w in per.items():
        row: dict[str, Any] = {"alarme": w["alarme"], "spaet": w["spaet"]}
        entry = (wallets or {}).get(wallet)
        row["tag"] = entry.name if entry else wallet[:4] + "…" + wallet[-4:]
        row["liste"] = entry.stats_text() if entry else "nicht in der Liste"
        beurteilbar = [m for m, d in w["mints"].items() if ex.beurteilbar(d["t"]) or ex.nachlauf_bekannt(m)]
        grad = [m for m in beurteilbar if m in ex.graduiert or ex.dex_graduiert(m)]
        row["graduation"] = {"n": len(beurteilbar), "k": len(grad), "wilson": wilson(len(grad), len(beurteilbar)) if beurteilbar else None}
        for h in horizons:
            mults: list[float] = []
            cons: list[float] = []
            tot = lebt = 0
            for m, d in w["mints"].items():
                nl = _nachlauf_at(ex, m, h)
                if nl is None:
                    continue
                tot += 1
                alive = not nl.get("fehlt") and nl.get("liq_usd") is not None and float(nl["liq_usd"]) >= UEBERLEBEN_LIQ_USD
                lebt += 1 if alive else 0
                r = follower_return(d["p0"], nl.get("preis_native"), fee_bps) if alive else None
                if r is not None:
                    mults.append(r + 1.0)
                cons.append((r + 1.0) if r is not None else 0.0)  # fehlt oder unverkäuflich: Totalverlust (konservativ)
            row[f"nach_{int(h)}"] = {
                "n": tot, "lebt": lebt, "wilson": wilson(lebt, tot) if tot else None,
                "median_x": round(statistics.median(mults), 3) if mults else None,
                "anteil_ueber_1x": round(sum(1 for x in mults if x >= 1.0) / len(mults), 3) if mults else None,
                "median_x_konservativ": round(statistics.median(cons), 3) if cons else None,
            }
        out["wallets"][wallet] = row
    return out


def format_wallet_report(rep: dict[str, Any]) -> str:
    if not rep["wallets"]:
        return "Keine FOLGE-Alarme in den Aufzeichnungen (live --wallets DATEI --record live.jsonl)."
    lines = [
        f"Wallet-Folge: {len(rep['wallets'])} Wallets mit FOLGE-Alarmen; Kurs-Vielfaches = DexScreener-Preis nach dem Horizont gegen den "
        f"Kurvenpreis beim Alarm, Gebühr {rep['fee_bps'] / 100:.2f} % je Seite, ohne Preisimpact; konservativ: fehlt/unverkäuflich = 0x"
    ]
    for wallet, row in sorted(rep["wallets"].items(), key=lambda kv: -kv[1]["alarme"]):
        g = row["graduation"]
        gw = f" [{g['wilson'][0]:.0%}–{g['wilson'][1]:.0%}]" if g["wilson"] else ""
        head = f"{row['tag']} ({wallet[:8]}…): {row['alarme']} Alarme" + (f", {row['spaet']} spät gesehen" if row["spaet"] else "")
        head += f" · Liste: {row['liste']} · Graduation {g['k']}/{g['n']}{gw}"
        lines.append(head)
        for h in rep["horizonte"]:
            d = row.get(f"nach_{int(h)}") or {}
            if not d.get("n"):
                lines.append(f"    +{int(h) // 3600} h: noch kein Nachlauf (`quellen nachlauf`)")
                continue
            lw = f" [{d['wilson'][0]:.0%}–{d['wilson'][1]:.0%}]" if d.get("wilson") else ""
            med = f"{d['median_x']:.2f}x" if d.get("median_x") is not None else "–"
            over = f"{d['anteil_ueber_1x']:.0%}" if d.get("anteil_ueber_1x") is not None else "–"
            cons = f"{d['median_x_konservativ']:.2f}x" if d.get("median_x_konservativ") is not None else "–"
            lines.append(f"    +{int(h) // 3600} h: lebt {d['lebt']}/{d['n']}{lw} · Median {med} (über 1x: {over}) · konservativ {cons}")
    lines.append("Lesart: erst ab 10 beurteilbaren Alarmen je Wallet; Wilson-Untergrenze über der Kontrollgruppe aus `tape report --extern` zählt.")
    return "\n".join(lines)
