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
from .pump import LAMPORTS_PER_SOL, WSOL_MINT, ZERO_PUBKEY

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
    spaet: int = 0  # davon erst durch ein Wallet gesehen: t0 ist kein Launch, keine frühen Käufer daraus
    beurteilbar: int = 0  # davon mit Label (Graduation oder Nachlauf am Horizont)
    kontrollen: int = 0  # beurteilbare Kontroll-Coins
    kontroll_rate: float | None = None
    kontroll_wilson: tuple[float, float] | None = None
    alarm_rate: float | None = None  # Trefferrate der beurteilbaren Alarm-Coins (höher als die Kontrollen: Selektion)
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
    Außenquellen, je Wallet Trefferquote mit Wilson-Intervall.

    Vergleichswert je Wallet: die erwartete Trefferzahl aus den Raten der Gruppen, in denen seine Coins liegen
    (Alarm-Coins haben eine viel höhere Rate als die Kontrollgruppe, weil der Sniper sie ausgesucht hat). Ein Wallet
    ist Kandidat, wenn die Wilson-Untergrenze seiner Quote über dieser gruppengleichen Erwartung liegt. Coins, die erst
    durch ein Wallet gesehen wurden (``spaet``), haben kein Launch-t0 und liefern keine frühen Käufer.
    """
    from .replay import wilson

    coins: dict[str, dict[str, Any]] = {}
    for r in iter_rows(tape_path):
        mint = r.get("mint")
        if not mint or r.get("ts") is None:
            continue
        c = coins.setdefault(mint, {"t0": float(r.get("t0") or 0), "dev": r.get("dev"), "control": bool(r.get("control")), "spaet": False, "rows": []})
        c["spaet"] = c["spaet"] or bool(r.get("spaet"))
        c["rows"].append(r)
    res = ScoutResult(coins=len(coins))
    if not coins:
        res.lesart = "Tape leer: `live --tape live_tape.jsonl --tape-sample 0.1` aufzeichnen"
        return res
    early: dict[str, dict[str, Any]] = {}  # wallet -> {coins: set, good: set, bad: set, first: t, last: t}
    labels: dict[str, bool | None] = {}
    for mint, c in coins.items():
        rows = c["rows"]
        label = _good(ex, mint, horizon_s)
        labels[mint] = label
        if label is not None:
            res.beurteilbar += 1
            if c["control"]:
                res.kontrollen += 1
        if c["spaet"]:
            res.spaet += 1
            continue  # t0 is the wallet's buy, not the launch: the buyers after it are followers, not early birds
        first_slot = min(int(r.get("slot") or 0) for r in rows)
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
    judged = {m for m in coins if labels[m] is not None}
    good_controls = sum(1 for m in judged if coins[m]["control"] and labels[m] is True)
    if res.kontrollen:
        res.kontroll_rate = good_controls / res.kontrollen
        res.kontroll_wilson = wilson(good_controls, res.kontrollen)
    alarm_judged = [m for m in judged if not coins[m]["control"]]
    if alarm_judged:
        res.alarm_rate = sum(1 for m in alarm_judged if labels[m] is True) / len(alarm_judged)
    if res.beurteilbar:
        res.grundrate_alle = sum(1 for m in judged if labels[m] is True) / res.beurteilbar
    rate_of = {m: (res.kontroll_rate if coins[m]["control"] else res.alarm_rate) for m in judged}
    for addr, w in early.items():
        n_total = len(w["coins"])
        if n_total / max(len(coins), 1) > max_anteil:
            res.bots += 1  # früh in jedem fünften Coin: Sniper- oder Bump-Bot, kein Narrativ-Käufer
            continue
        mine = [m for m in w["good"] | w["bad"]]
        n, k = len(mine), len(w["good"])
        if n < min_coins:
            continue
        wi = wilson(k, n)
        expected = [rate_of[m] for m in mine if rate_of.get(m) is not None]
        if wi is None or len(expected) < n:
            continue
        bar = sum(expected) / n
        if wi[0] <= bar:
            continue
        res.kandidaten.append(
            {
                "wallet": addr, "treffer": k, "coins": n, "frueh_in": n_total, "wilson": [round(wi[0], 4), round(wi[1], 4)],
                "erwartet": round(bar, 4), "seit": w["first"], "zuletzt": w["last"],
            }
        )
    res.kandidaten.sort(key=lambda c: (-(c["wilson"][0] - c["erwartet"]), -c["coins"]))
    rates = []
    if res.alarm_rate is not None:
        rates.append(f"Alarm-Coins {res.alarm_rate:.1%} (n={len(alarm_judged)})")
    if res.kontroll_rate is not None:
        rates.append(f"Kontrollgruppe {res.kontroll_rate:.1%} (n={res.kontrollen})")
    res.lesart = (
        f"{res.coins} Coins im Tape ({res.spaet} spät gesehen, ohne Launch-t0), {res.beurteilbar} beurteilbar, {res.wallets} Wallets früh dabei, "
        f"{res.bots} als Bot ausgeschlossen; Trefferraten je Gruppe: {', '.join(rates) or 'keine Labels (Außenquellen fehlen)'}; "
        f"Kandidat = Wilson-Untergrenze über der gruppengleichen Erwartung bei mindestens {min_coins} beurteilbaren Coins"
        + ("" if res.kontrollen >= 20 else "; unter 20 Kontroll-Coins ist die Kontrollrate selbst unsicher")
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
            notiz=f"Wilson {c['wilson'][0]:.0%}–{c['wilson'][1]:.0%} gegen erwartet {c['erwartet']:.0%}, früh in {c['frueh_in']} Coins, seit {seit}",
        )
        out.append(format_wallet_line(e))
    return out


# --- Report: was aus den FOLGE-Alarmen wurde --------------------------------------------------------------------------


def _curve_price_sol(curve: dict[str, Any] | None) -> float | None:
    """SOL je ganzem Token aus den virtuellen Reserven des Records (9 bzw. 6 Dezimalen), wie paper.curve_price.
    None für eine Kurve, die nicht in SOL quotiert ist (USDC): deren Reserven haben andere Dezimalen."""
    if not curve or curve.get("quote_mint") not in (None, WSOL_MINT, ZERO_PUBKEY):
        return None
    vq, vt = curve.get("virtual_quote_reserves"), curve.get("virtual_token_reserves")
    if not vq or not vt or float(vt) <= 0:
        return None
    return (float(vq) / LAMPORTS_PER_SOL) / (float(vt) / 1e6)


def _nachlauf_at(ex: Extern, mint: str, horizon_s: float, t_folge: float | None = None) -> dict[str, Any] | None:
    """Die Nachlauf-Zeile zum Horizont, nur wenn sie zum FOLGE-Zeitpunkt passt: ``quellen nachlauf`` misst ab dem
    ersten Alarm des Coins; kam der FOLGE lange nach einem GO, gehört die Zeile zum GO, nicht zum Wallet-Kauf."""
    rows = [r for r in ex.nachlauf.get(mint, ()) if abs(float(r.get("nach_s") or 0) - horizon_s) < 1.0]
    if not rows:
        return None
    row = rows[-1]
    alter = row.get("alter_s")
    if alter is not None and float(alter) > 2 * horizon_s:
        return None  # verspäteter Schnappschuss, wie in extern_summary
    if t_folge is not None and row.get("t_ref") is not None and abs(float(row["t_ref"]) - t_folge) > 0.1 * horizon_s:
        return None
    return row


def _preis_sol(row: dict[str, Any]) -> float | None:
    """preis_native der Nachlauf-Zeile als SOL je Token; None, wenn das Paar gegen etwas anderes quotiert ist."""
    quote = row.get("quote")
    if quote not in (None, WSOL_MINT):
        return None
    return row.get("preis_native")


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
        w = per.setdefault(wallet, {"alarme": 0, "mints": {}, "spaet": 0, "keine_sol_kurve": 0})
        if mint in w["mints"]:
            continue  # ein Alarm je Coin und Wallet
        w["alarme"] += 1
        w["spaet"] += 1 if rec.get("spaet") else 0
        p0 = _curve_price_sol(rec.get("curve"))
        w["keine_sol_kurve"] += 1 if (rec.get("curve") and p0 is None) else 0
        w["mints"][mint] = {"t": float(rec.get("alert_at") or 0), "p0": p0}
    out: dict[str, Any] = {"wallets": {}, "horizonte": list(horizons), "fee_bps": fee_bps}
    for wallet, w in per.items():
        row: dict[str, Any] = {"alarme": w["alarme"], "spaet": w["spaet"], "keine_sol_kurve": w["keine_sol_kurve"]}
        entry = (wallets or {}).get(wallet)
        row["tag"] = entry.name if entry else wallet[:4] + "…" + wallet[-4:]
        row["liste"] = entry.stats_text() if entry else "nicht in der Liste"
        beurteilbar = [m for m, d in w["mints"].items() if ex.beurteilbar(d["t"]) or ex.nachlauf_bekannt(m)]
        grad = [m for m in beurteilbar if m in ex.graduiert or ex.dex_graduiert(m)]
        row["graduation"] = {"n": len(beurteilbar), "k": len(grad), "wilson": wilson(len(grad), len(beurteilbar)) if beurteilbar else None}
        for h in horizons:
            mults: list[float] = []  # Vielfache der Überlebenden mit SOL-Preis auf beiden Seiten
            cons: list[float] = []  # alle: fehlt, unverkäuflich oder ohne SOL-Preis zählt als Totalverlust
            tot = lebt = passt_nicht = ohne_preis = 0
            for m, d in w["mints"].items():
                nl = _nachlauf_at(ex, m, h, d["t"])
                if nl is None:
                    passt_nicht += 1 if _nachlauf_at(ex, m, h) is not None else 0  # Zeile gehört zu einem früheren Alarm
                    continue
                tot += 1
                alive = not nl.get("fehlt") and nl.get("liq_usd") is not None and float(nl["liq_usd"]) >= UEBERLEBEN_LIQ_USD
                lebt += 1 if alive else 0
                p1 = _preis_sol(nl) if alive else None
                r = follower_return(d["p0"], p1, fee_bps) if alive else None
                if alive and r is None:
                    ohne_preis += 1  # SOL-Preis fehlt auf einer Seite (USDC-Kurve, Paar gegen USDC)
                if r is not None:
                    mults.append(r + 1.0)
                cons.append((r + 1.0) if r is not None else 0.0)
            row[f"nach_{int(h)}"] = {
                "n": tot, "lebt": lebt, "wilson": wilson(lebt, tot) if tot else None,
                "median_x_ueberlebende": round(statistics.median(mults), 3) if mults else None,
                "anteil_ueber_1x": round(sum(1 for x in cons if x >= 1.0) / len(cons), 3) if cons else None,
                "median_x_konservativ": round(statistics.median(cons), 3) if cons else None,
                "nachlauf_passt_nicht": passt_nicht, "ohne_sol_preis": ohne_preis,
            }
        out["wallets"][wallet] = row
    return out


def format_wallet_report(rep: dict[str, Any]) -> str:
    if not rep["wallets"]:
        return "Keine FOLGE-Alarme in den Aufzeichnungen (live --wallets DATEI --record live.jsonl)."
    lines = [
        f"Wallet-Folge: {len(rep['wallets'])} Wallets mit FOLGE-Alarmen; Kurs-Vielfaches = DexScreener-Preis (SOL je Token, [Snippet]) nach dem "
        f"Horizont gegen den Kurvenpreis beim FOLGE, Gebühr {rep['fee_bps'] / 100:.2f} % je Seite, ohne Preisimpact. "
        "'über 1x' und 'konservativ' zählen fehlt, unverkäuflich (< 1 000 USD Liquidität) und fehlenden SOL-Preis als 0x; "
        "'Median Überlebende' nur über die Coins mit Paar."
    ]
    for wallet, row in sorted(rep["wallets"].items(), key=lambda kv: -kv[1]["alarme"]):
        g = row["graduation"]
        gw = f" [{g['wilson'][0]:.0%}–{g['wilson'][1]:.0%}]" if g["wilson"] else ""
        head = f"{row['tag']} ({wallet[:8]}…): {row['alarme']} Alarme" + (f", {row['spaet']} spät gesehen" if row["spaet"] else "")
        if row.get("keine_sol_kurve"):
            head += f", {row['keine_sol_kurve']} ohne SOL-Kurve"
        head += f" · Liste: {row['liste']} · Graduation {g['k']}/{g['n']}{gw}"
        lines.append(head)
        for h in rep["horizonte"]:
            d = row.get(f"nach_{int(h)}") or {}
            if not d.get("n"):
                note = f" ({d['nachlauf_passt_nicht']} Zeilen gehören zu einem früheren Alarm des Coins)" if d.get("nachlauf_passt_nicht") else ""
                lines.append(f"    +{int(h) // 3600} h: noch kein Nachlauf (`quellen nachlauf`){note}")
                continue
            lw = f" [{d['wilson'][0]:.0%}–{d['wilson'][1]:.0%}]" if d.get("wilson") else ""
            med = f"{d['median_x_ueberlebende']:.2f}x" if d.get("median_x_ueberlebende") is not None else "–"
            over = f"{d['anteil_ueber_1x']:.0%}" if d.get("anteil_ueber_1x") is not None else "–"
            cons = f"{d['median_x_konservativ']:.2f}x" if d.get("median_x_konservativ") is not None else "–"
            extra = []
            if d.get("ohne_sol_preis"):
                extra.append(f"{d['ohne_sol_preis']} ohne SOL-Preis")
            if d.get("nachlauf_passt_nicht"):
                extra.append(f"{d['nachlauf_passt_nicht']} Zeilen zu einem früheren Alarm")
            lines.append(
                f"    +{int(h) // 3600} h: lebt {d['lebt']}/{d['n']}{lw} · über 1x {over} · konservativ {cons} · Median Überlebende {med}"
                + (f" ({', '.join(extra)})" if extra else "")
            )
    lines.append("Lesart: erst ab 10 beurteilbaren Alarmen je Wallet; 'über 1x' und 'konservativ' zählen, der Median der Überlebenden beschreibt nur.")
    return "\n".join(lines)
