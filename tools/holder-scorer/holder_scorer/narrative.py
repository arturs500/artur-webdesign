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
        self._items: deque[tuple[float, str, str, str]] = deque()  # (time, mint, norm name, norm symbol)

    def _prune(self, now: float) -> None:
        while self._items and (now - self._items[0][0] > self.window_s or len(self._items) > self.max_items):
            self._items.popleft()

    def is_copycat(self, mint: str, name: str | None, symbol: str | None, now: float) -> bool:
        self._prune(now)
        n, s = normalize(name), normalize(symbol)
        for _, other, on, os_ in self._items:
            if other == mint:
                continue
            if n and len(n) >= 3 and on == n:
                return True
            if s and len(s) >= 4 and os_ == s:
                return True
        return False

    def register(self, mint: str, name: str | None, symbol: str | None, now: float) -> None:
        self._prune(now)
        self._items.append((now, mint, normalize(name), normalize(symbol)))


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
