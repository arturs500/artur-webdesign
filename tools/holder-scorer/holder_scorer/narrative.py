"""A crude, honest proxy for "good narrative".

Nobody can measure a narrative on-chain. What can be measured: real social links,
a description and image in the metadata, a name that is not a throwaway string,
a name that is not a copy of a coin launched minutes ago, and a hit in a keyword
list the user maintains (``--narratives datei.txt``, one trend word per line).
The score is 0..100 and is meant for filters like "Narrativ >= 60", nothing more.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

GENERIC_NAMES = {"test", "aaa", "asdf", "token", "coin", "meme", "pump", "new", "abc", "xxx", "lol"}
_NORM = re.compile(r"[^a-z0-9]+")


def normalize(text: str | None) -> str:
    return _NORM.sub("", (text or "").lower())


def narrative_score(
    name: str | None,
    symbol: str | None,
    metadata: dict[str, Any] | None,
    socials_count: int | None,
    copycat: bool,
    keywords: Iterable[str] = (),
) -> tuple[int, list[str]]:
    """Returns (score 0..100, reasons in German for the record line)."""
    score = 30
    reasons: list[str] = []
    md = metadata or {}
    if socials_count:
        score += min(3, int(socials_count)) * 15
        reasons.append(f"{socials_count} Social-Links")
    desc = str(md.get("description") or "").strip()
    if len(desc) >= 40:
        score += 10
        reasons.append("Beschreibung")
    if md.get("image"):
        score += 5
    text = " ".join([name or "", symbol or "", desc]).lower()
    hits = [k for k in keywords if k and k.lower() in text]
    if hits:
        score += 25
        reasons.append("Trend: " + ", ".join(sorted(set(hits))[:3]))
    n = normalize(name)
    if not n or len(n) < 3 or n in GENERIC_NAMES or n.isdigit() or "test" in n:
        score -= 20
        reasons.append("Wegwerf-Name")
    if copycat:
        score -= 30
        reasons.append("KOPIE")
    return max(0, min(100, score)), reasons


class NameRegistry:
    """Remembers recent launch names to spot copycats (the same name or symbol minutes later)."""

    def __init__(self, window_s: float = 3600.0, max_items: int = 20000):
        self.window_s = window_s
        self.max_items = max_items
        self._items: deque[tuple[float, str, str, str, int]] = deque()  # (time, mint, norm name, norm symbol, order)
        self._order: dict[str, int] = {}  # mint -> registration order: a copy is only what was registered *before* this mint
        self._seq = 0

    def _prune(self, now: float) -> None:
        while self._items and (now - self._items[0][0] > self.window_s or len(self._items) > self.max_items):
            _, mint, _, _, _ = self._items.popleft()
            self._order.pop(mint, None)

    def is_copycat(self, mint: str, name: str | None, symbol: str | None, now: float) -> bool:
        """True when an *earlier registered* launch of the last hour carried the same name or symbol.

        Directional since 0.3.5: the original of a wave does not become a copy because imitators followed it
        (that produced a false WIDERRUF after GO). Registration order decides, so two launches in the same second
        are still ordered. An unregistered mint is compared against everything seen.
        """
        self._prune(now)
        n, s = normalize(name), normalize(symbol)
        own = self._order.get(mint, self._seq + 1)
        for _t, other, on, os_, order in self._items:
            if other == mint or order >= own:
                continue
            if n and len(n) >= 3 and on == n:
                return True
            if s and len(s) >= 4 and os_ == s:
                return True
        return False

    def register(self, mint: str, name: str | None, symbol: str | None, now: float) -> None:
        self._prune(now)
        self._seq += 1
        self._items.append((now, mint, normalize(name), normalize(symbol), self._seq))
        self._order.setdefault(mint, self._seq)


# --- Themen-Wellen: das früheste Narrativ-Signal im eigenen Datenstrom (0.3.3, OQ-028) ------------------------------
#
# Copycat-Deployer reagieren in Sekunden auf einen Auslöser. Mehrere Launches mit demselben Begriff von
# verschiedenen Devs in wenigen Minuten verraten das Thema, bevor ein einzelner Coin Handelsdaten hat. Bisher
# wurde diese Welle nur negativ genutzt (KOPIE). Das Register zählt je Begriff Launches und Devs im Fenster
# gegen die Grundrate der letzten Stunden; die Live-Engine bestimmt daraus Rang und Zufluss je Coin. Alles ohne
# zusätzliche RPC-Aufrufe. Record-only: kein Gate, bis ein Zeitsplit zeigt, dass der Wellen-Rang Rendite trennt.

STOPWORDS = GENERIC_NAMES | {
    "the", "and", "for", "with", "from", "this", "that", "official", "sol", "solana", "inu", "fun", "pumpfun",
    "dot", "com", "org", "net", "www", "http", "https", "ipfs", "coins", "memes", "just", "now", "its", "are",
    "you", "your", "our", "all", "not", "but", "has", "was", "will", "one", "day", "get", "out", "can", "who",
    "what", "when", "how", "launch", "launched", "community", "first", "ever", "only", "real", "true", "best",
}
_SPLIT = re.compile(r"[^a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")
_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:www\.)?([^\s/?#@]+)([^\s?#]*)", re.I)


def terms(*texts: str | None, max_terms: int = 12) -> set[str]:
    """Begriffe aus Name, Symbol oder Beschreibung: klein, ohne Sonderzeichen und Füllwörter, ab drei Zeichen."""
    out: set[str] = set()
    for text in texts:
        if not text:
            continue
        for tok in _SPLIT.split(_CAMEL.sub(" ", str(text)).lower()):
            if len(tok) < 3 or tok.isdigit() or tok in STOPWORDS:
                continue
            out.add(tok)
            if len(out) >= max_terms:
                return out
    return out


def link_anchors(metadata: dict[str, Any] | None) -> set[str]:
    """Normalisierte Ziele der Social-Links (Host + Pfad, ohne Schema, www, Query); twitter.com → x.com.

    Eine nackte Domain wie x.com oder t.me sagt nichts; pump.fun-eigene Links ebenfalls nicht.
    """
    out: set[str] = set()
    for key in ("twitter", "telegram", "website"):
        val = (metadata or {}).get(key)
        if not isinstance(val, str) or len(val.strip()) < 4:
            continue
        m = _URL.match(val.strip())
        if not m:
            continue
        host, path = m.group(1).lower(), m.group(2).rstrip("/").lower()
        if host in ("twitter.com", "mobile.twitter.com", "x.com"):
            host = "x.com"
        if host in ("x.com", "t.me", "telegram.me", "discord.gg", "discord.com") and not path:
            continue
        if host.endswith("pump.fun") or "." not in host:
            continue
        out.add(host + path)
    return out


@dataclass
class ThemeStats:
    term: str
    n_recent: int  # Launches mit dem Begriff im Fenster
    devs_recent: int  # verschiedene Creator darunter
    baseline: float  # erwartete Launches je Fenster aus der Historie
    ratio: float  # n_recent / max(baseline, floor)
    wave: bool
    position: int | None  # 1 = ältester Launch des Begriffs im Fenster
    mints: list[str]  # Mints im Fenster, älteste zuerst


class ThemeRegistry:
    """Zählt Begriffe über alle Launches: Welle = viele Launches von vielen Devs weit über der Grundrate."""

    def __init__(
        self,
        window_s: float = 600.0,
        history_s: float = 6 * 3600.0,
        min_launches: int = 4,
        min_devs: int = 3,
        min_ratio: float = 4.0,
        floor_rate: float = 0.5,
    ):
        self.window_s = window_s
        self.history_s = history_s
        self.min_launches = min_launches
        self.min_devs = min_devs
        self.min_ratio = min_ratio
        self.floor_rate = floor_rate
        self._by_term: dict[str, deque[tuple[float, str, str]]] = {}  # term -> (time, mint, creator)
        self._terms_of: dict[str, set[str]] = {}
        self._first_seen: float | None = None

    def register(self, mint: str, creator: str | None, texts: Iterable[str | None], now: float, raw: bool = False) -> set[str]:
        """Begriffe eines Launches aufnehmen (``raw``: ``texts`` sind schon fertige Schlüssel, z. B. Link-Anker)."""
        new = {str(t) for t in texts if t} if raw else terms(*texts)
        seen = self._terms_of.setdefault(mint, set())
        added = new - seen
        for t in added:
            self._by_term.setdefault(t, deque()).append((now, mint, creator or ""))
        seen |= added
        if self._first_seen is None or now < self._first_seen:
            self._first_seen = now
        self._prune(now)
        return added

    def terms_of(self, mint: str) -> set[str]:
        return set(self._terms_of.get(mint, ()))

    def _prune(self, now: float) -> None:
        cutoff = now - self.history_s
        for term in list(self._by_term):
            dq = self._by_term[term]
            while dq and dq[0][0] < cutoff:
                _, mint, _ = dq.popleft()
                s = self._terms_of.get(mint)
                if s is not None:
                    s.discard(term)
                    if not s:
                        self._terms_of.pop(mint, None)
            if not dq:
                del self._by_term[term]

    def stats(self, term: str, now: float, mint: str | None = None) -> ThemeStats | None:
        dq = self._by_term.get(term)
        entries = [e for e in (dq or ()) if e[0] >= now - self.history_s]  # pruning itself happens on register
        if not entries:
            return None
        start = now - self.window_s
        recent = sorted((e for e in entries if start < e[0] <= now), key=lambda e: e[0])
        older = [e for e in entries if e[0] <= start]
        covered = min(self.history_s, now - (self._first_seen if self._first_seen is not None else now)) - self.window_s
        buckets = max(1.0, covered / self.window_s)
        baseline = len(older) / buckets
        ratio = len(recent) / max(baseline, self.floor_rate)
        devs = len({e[2] for e in recent})
        mints = [e[1] for e in recent]
        wave = len(recent) >= self.min_launches and devs >= self.min_devs and ratio >= self.min_ratio
        position = mints.index(mint) + 1 if mint in mints else None
        return ThemeStats(term, len(recent), devs, round(baseline, 3), round(ratio, 2), wave, position, mints)

    def theme_for(self, mint: str, now: float, min_recent: int = 2) -> ThemeStats | None:
        """Der auffälligste Begriff eines Coins: Welle vor Verhältnis vor Anzahl; None ohne zweiten Launch."""
        best: ThemeStats | None = None
        for term in self._terms_of.get(mint, ()):
            s = self.stats(term, now, mint)
            if s is None or s.n_recent < min_recent:
                continue
            if best is None or (s.wave, s.ratio, s.n_recent) > (best.wave, best.ratio, best.n_recent):
                best = s
        return best


def theme_line(narrativ: dict[str, Any] | None) -> str | None:
    """Kurzzeile für die Nachricht, z. B. ``doge · 5 L/10min · 4 Devs · WELLE · Rang 1/4 · 3.2 SOL · Quelle ×2``."""
    if not narrativ:
        return None
    parts: list[str] = []
    if narrativ.get("thema"):
        parts.append(f"{narrativ['thema']} · {narrativ['n']} L/{int(narrativ.get('fenster_s', 600) // 60)}min · {narrativ['devs']} Devs")
        if narrativ.get("welle"):
            parts.append("WELLE")
        if narrativ.get("rang"):
            parts.append(f"Rang {narrativ['rang']}/{narrativ.get('beobachtet', '?')} · {narrativ.get('zufluss_thema_sol', 0):.1f} SOL")
    q = narrativ.get("quelle")
    if q:
        parts.append(f"Quelle ×{q['n']}")
    return " · ".join(parts) or None


def load_keywords(path: str | None) -> list[str]:
    if not path:
        return []
    out: list[str] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                word = line.strip()
                if word and not word.startswith("#"):
                    out.append(word)
    except OSError:
        return []
    return out
