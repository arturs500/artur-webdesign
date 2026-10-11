"""Wallet-Prüfung (0.3.7): halten Wallets, die mit dem Dev oder untereinander verbunden sind, einen großen Teil des Floats?

Was man auf Solscan von Hand prüft, rechnet dieses Modul aus den Wallet-Profilen: Woher kam das SOL der größten
Halter (Finanzierer = Fee-Payer der ersten Transaktion, siehe ``collect._early_wallets``), hängt es am Dev, an der
Quelle des Devs oder an einer gemeinsamen Quelle mehrerer Top-Halter? Der typische Rug auf der Kurve läuft genau so:
Dev und Sniper-Wallets aus einer Hand, die Sniper verkaufen in die Käufer. Börsen-Hot-Wallets (``funder_busy``) gelten
nicht als Verbindung, sonst wäre jeder Halter mit einer Binance-Auszahlung mit jedem anderen verbunden.

Keine Solscan-API (Abo und Schlüssel, Eskalationsliste in CLAUDE.md): dieselben Daten kommen über den vorhandenen RPC
(OQ-034). Die Solscan-Links in den Nachrichten (notify.py) sind für die Prüfung von Hand.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .collect import WalletProfile

TOP_HOLDERS = 8  # so many of the largest non-dev holders are profiled before a GO


@dataclass
class VerbundResult:
    share: float  # supply share held by top holders linked to the dev or to each other
    wallets: int  # number of linked top holders
    top: int  # top holders considered
    checked: int  # of these, holders with a wallet profile
    unchecked_share: float  # supply share of top holders without a profile (lookup failed or still missing)
    fresh_share: float  # supply share of checked top holders whose wallet is fresh (record only, no gate)
    linked: list[dict[str, Any]] = field(default_factory=list)  # address, share, reason; largest first

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def top_holders(balances: dict[str, int], devs: set[str], n: int = TOP_HOLDERS) -> list[tuple[str, int]]:
    """The ``n`` largest holders outside the dev addresses, largest first (ties by address for a stable order)."""
    rows = [(o, a) for o, a in balances.items() if a > 0 and o not in devs]
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:n]


def holder_verbund(
    balances: dict[str, int],
    supply: int,
    profiles: dict[str, WalletProfile],
    *,
    devs: set[str],
    creator_funder: str | None,
    top: int = TOP_HOLDERS,
) -> VerbundResult:
    """Supply share of the top holders that hang on the dev or on each other.

    A top holder is linked when (first match wins): it funded the dev; the dev funded it; it shares the dev's
    funder; another top holder funded it, or it funded another top holder; it shares a funder with at least one
    other top holder. Funders that look like exchange hot wallets (``funder_busy is True``) never link. Unknown is
    not clean: top holders without a profile are reported as ``unchecked_share``.
    """
    holders = top_holders(balances, devs, top)
    supply = max(int(supply), 1)
    addrs = {o for o, _ in holders}
    groups: dict[str, list[str]] = {}
    for o, _ in holders:
        p = profiles.get(o)
        if p is not None and p.funder and p.funder_busy is not True and p.funder not in devs:
            groups.setdefault(p.funder, []).append(o)
    funded_others = {p.funder for o, _ in holders if (p := profiles.get(o)) is not None and p.funder in addrs}

    reasons: dict[str, str] = {}
    for o, _ in holders:
        p = profiles.get(o)
        if p is None:
            continue
        exchange = p.funder_busy is True
        if creator_funder and o == creator_funder:
            reasons[o] = "finanzierte den Dev"
        elif p.funder and p.funder in devs:
            reasons[o] = "vom Dev finanziert"
        elif creator_funder and p.funder == creator_funder and not exchange:
            reasons[o] = "gleiche Quelle wie der Dev"
        elif p.funder and p.funder in addrs:
            reasons[o] = "von einem Top-Halter finanziert"
        elif o in funded_others:
            reasons[o] = "finanzierte einen Top-Halter"
        elif p.funder and not exchange and len(groups.get(p.funder, [])) >= 2:
            reasons[o] = f"gemeinsame Quelle mit {len(groups[p.funder]) - 1} Top-Halter(n)"

    linked = [
        {"wallet": o, "anteil": round(a / supply, 4), "grund": reasons[o]} for o, a in holders if o in reasons
    ]
    checked = [(o, a) for o, a in holders if o in profiles]
    return VerbundResult(
        share=round(sum(a for o, a in holders if o in reasons) / supply, 4),
        wallets=len(linked),
        top=len(holders),
        checked=len(checked),
        unchecked_share=round(sum(a for o, a in holders if o not in profiles) / supply, 4),
        fresh_share=round(sum(a for o, a in checked if profiles[o].is_fresh) / supply, 4),
        linked=linked,
    )


def verbund_line(v: dict[str, Any] | None) -> str | None:
    """Short text for the message: share, wallets and the main reason."""
    if not v:
        return None
    text = f"Verbund {v['share'] * 100:.0f} %"
    if v.get("wallets"):
        text += f" in {v['wallets']} Wallets ({v['linked'][0]['grund']})" if v.get("linked") else f" in {v['wallets']} Wallets"
    text += f" · geprüft {v.get('checked', 0)}/{v.get('top', 0)}"
    return text
