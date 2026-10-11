"""Fairness-Gate (0.3.4): die Prinzipien aus docs/fair_launch.md als Bedingungen für BLICK und GO.

Die Türsteher des Marktes sind Bots mit Regeln; jede ihrer Warnungen ist zugleich etwas, das Halter schädigt.
Dieses Gate macht die Prinzipien eines fairen Launches zur Pflicht für einen Call:

* **Dev-Anteil** klein (Kauf und Bestand), **kein Dev-Verkauf** vor dem GO.
* **Kein Bundle**: wenig Supply und wenige fremde Wallets im Create-Fenster.
* **Keine Kopie** eines Launches der letzten Stunde (die zehnte Kopie einer Welle).
* **Kein unsichtbarer Float**, **keine Bots/Wash**.
* **Historie**: Dev-Wallet nicht frisch, keine Serie toter Launches – erst prüfbar, wenn die Creator-Abfrage da ist
  (GO wartet darauf, solange ein RPC vorhanden ist).
* **Metadaten**: Bild und Social-Links – erst prüfbar, wenn der Abruf da ist (GO wartet darauf, solange
  Nebenabfragen laufen).
* **Wallets** (0.3.7, OQ-034): Die größten Halter dürfen nicht zu einem großen Teil am Dev oder aneinander hängen
  (wallets.py, die Prüfung, die man sonst auf Solscan von Hand macht). Die Creator-Historie muss vollständig
  gescannt sein, und eine fehlgeschlagene Creator-Abfrage ist ein Fehlen, kein Bestehen.

Schnelle Prüfungen (Dev, Bundle, Kopie, Float, Bots) gelten schon für BLICK; die langsamen (Historie, Metadaten)
erst für GO. Sagt der Score GO und ein Prinzip ist verletzt, geht einmal ⛔ GESPERRT heraus (Aufzeichnung, keine
Handy-Nachricht im Standard), damit `tape report --tiers GESPERRT` später zeigt, ob die gesperrten Coins
schlechter liefen als die GO-Coins. So bleibt die Verschärfung messbar (R2, R4 in docs/experte.md).

Unbekannt zählt nicht als sauber: fehlende Metadaten oder eine nicht ladbare Historie sind ein Fehlen, kein
Freifahrtschein. Schwellen je Stufe sind Startwerte ohne Daten (OQ-031).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FairConfig:
    enabled: bool = True
    max_dev_share: float = 0.07  # Dev-Kauf und Dev-Bestand, Anteil der Supply (Stufe 1: 5 %, 3: 10 %)
    max_dev_sold: float = 0.0  # verkaufter Anteil des Dev-Kaufs vor dem GO (Stufe 3: 10 %)
    max_creation_buyers: int = 5  # fremde Käufer-Wallets im Create-Fenster (Stufe 1: 3, 3: 8)
    block_copycat: bool = True  # Name oder Symbol eines Launches der letzten Stunde
    require_creator_check: bool = True  # GO erst mit geladener Creator-Historie (nur mit RPC und Nebenabfragen)
    allow_fresh_creator: bool = False
    max_dead_share: float = 0.5  # Anteil toter Vor-Launches ab 3 Vor-Launches
    require_metadata: bool = True  # GO erst mit geladenen Metadaten (nur wenn Nebenabfragen laufen)
    min_socials: int = 2
    require_image: bool = True
    max_wash_share: float = 0.20
    max_bot_buy_share: float = 0.25
    max_hidden_float: float = 0.02
    # Wallet-Prüfung (0.3.7, OQ-034): Startwerte ohne Daten, gemessen über GO gegen GESPERRT
    require_complete_history: bool = True  # GO erst, wenn alle erfolgreichen Creator-Transaktionen gescannt sind
    require_wallet_check: bool = True  # GO erst nach der Prüfung der Top-Halter (wallets.py)
    max_verbund_share: float = 0.10  # Supply-Anteil in Top-Haltern, die am Dev oder aneinander hängen (Stufe 1: 5 %)

    @classmethod
    def for_stufe(cls, stufe: int) -> "FairConfig":
        if stufe <= 1:
            return cls(max_dev_share=0.05, max_creation_buyers=3, max_verbund_share=0.05)
        if stufe >= 3:
            return cls(
                max_dev_share=0.10, max_dev_sold=0.10, max_creation_buyers=8, block_copycat=False, require_creator_check=False,
                allow_fresh_creator=True, require_metadata=False, min_socials=1, require_image=False, max_wash_share=0.30, max_bot_buy_share=0.30,
                require_complete_history=False, require_wallet_check=False, max_verbund_share=0.20,
            )
        return cls()

    def summary(self) -> str:
        if not self.enabled:
            return "aus"
        parts = [f"Dev ≤ {self.max_dev_share:.0%}", f"Dev-Verkauf ≤ {self.max_dev_sold:.0%}", f"Create-Wallets ≤ {self.max_creation_buyers}"]
        if self.block_copycat:
            parts.append("Kopie gesperrt")
        if self.require_creator_check:
            parts.append("Historie Pflicht" + (" (vollständig)" if self.require_complete_history else ""))
        if self.require_wallet_check:
            parts.append(f"Wallet-Verbund < {self.max_verbund_share:.0%}")
        if self.require_metadata:
            parts.append(f"Socials ≥ {self.min_socials}" + (" + Bild" if self.require_image else ""))
        return ", ".join(parts)


@dataclass
class FairResult:
    ok: bool  # alle Prüfungen bestanden und nichts mehr offen: Bedingung für GO
    hard_ok: bool  # schnelle Prüfungen bestanden: Bedingung für BLICK
    fails: list[str] = field(default_factory=list)
    hard_fails: list[str] = field(default_factory=list)  # nur die schnellen Prüfungen (für WIDERRUF nach GO)
    pending: list[str] = field(default_factory=list)  # noch nicht prüfbar (lädt)
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fair_check(
    feats: Any,
    cfg: FairConfig,
    *,
    bundle_limit: float,
    copycat: bool,
    creator_done: bool,
    creator_possible: bool,
    metadata_state: str,  # ok | fehlt | fehler | laedt
    checks_possible: bool,
    creator_failed: bool = False,  # die Creator-Abfrage ist fertig, aber ohne Ergebnis (RPC-Fehler)
    creator_deep: str = "fertig",  # tiefer Scan einer unvollständigen Historie: offen | laedt | fertig | fehler
    creator_coverage: str | None = None,  # z. B. "150 von 640 Tx" für die Begründung
    wallet_state: str = "ungeprüft",  # Top-Halter-Prüfung: ok | offen | laedt | fehler | budget | ungeprüft
    verbund: dict[str, Any] | None = None,  # wallets.VerbundResult.to_dict()
) -> FairResult:
    """Alle Prinzipien gegen die aktuellen Merkmale prüfen. Unbekannt zählt nicht als sauber."""
    if not cfg.enabled:
        return FairResult(True, True, values={"aus": True})
    hard: list[str] = []
    slow: list[str] = []
    pending: list[str] = []
    v: dict[str, Any] = {}

    dev = max(float(getattr(feats, "dev_buy_share", 0) or 0.0), float(getattr(feats, "dev_holds_share", 0) or 0.0))
    v["dev_anteil"] = round(dev, 4)
    if dev > cfg.max_dev_share:
        hard.append(f"Dev-Anteil {dev * 100:.1f} % über {cfg.max_dev_share * 100:.0f} %")
    sold = float(getattr(feats, "dev_sold_share", 0) or 0.0)
    v["dev_verkauft"] = round(sold, 4)
    if float(getattr(feats, "dev_buy_share", 0) or 0.0) > 0 and sold > cfg.max_dev_sold:
        hard.append(f"Dev verkauft {sold * 100:.0f} %")
    share = getattr(feats, "creation_window_share", None)
    buyers = getattr(feats, "creation_slot_buyers", None)
    v["bundle"] = None if share is None else round(float(share), 4)
    v["bundle_wallets"] = buyers
    if share is not None and float(share) >= bundle_limit:
        hard.append(f"Bundle {float(share) * 100:.0f} % ab {bundle_limit * 100:.0f} %")
    if buyers is not None and int(buyers) > cfg.max_creation_buyers:
        hard.append(f"{int(buyers)} Wallets im Create-Block (höchstens {cfg.max_creation_buyers})")
    v["kopie"] = bool(copycat)
    if cfg.block_copycat and copycat:
        hard.append("Kopie eines Launches der letzten Stunde")
    hidden = getattr(feats, "hidden_float_share", None)
    v["unsichtbar"] = None if hidden is None else round(float(hidden), 4)
    if hidden is not None and float(hidden) >= cfg.max_hidden_float:
        hard.append(f"unsichtbarer Float {float(hidden) * 100:.1f} %")
    wash = getattr(feats, "wash_share", None)
    if wash is not None and float(wash) > cfg.max_wash_share and int(getattr(feats, "unique_traders", 0) or 0) >= 8:
        hard.append(f"Wash {float(wash) * 100:.0f} %")
    bots = getattr(feats, "bot_buy_share", None)
    if bots is not None and float(bots) > cfg.max_bot_buy_share:
        hard.append(f"Bots {float(bots) * 100:.0f} %")

    if creator_possible:
        if not creator_done:
            v["historie"] = "lädt"
            if cfg.require_creator_check:
                pending.append("Historie")
        elif creator_failed:
            # before 0.3.7 a failed lookup counted as an empty, clean history: a serial deployer got GO under RPC load
            v["historie"] = "fehler"
            if cfg.require_creator_check:
                slow.append("Historie nicht ladbar")
        else:
            prior = int(getattr(feats, "creator_prior_tokens", 0) or 0)
            dead = int(getattr(feats, "creator_dead", 0) or 0)
            grad = int(getattr(feats, "creator_graduated", 0) or 0)
            v["historie"] = f"{prior} Tok/{grad} grad/{dead} tot"
            if getattr(feats, "creator_is_fresh", False) and not cfg.allow_fresh_creator:
                slow.append("frisches Dev-Wallet")
            if prior >= 3 and dead / prior >= cfg.max_dead_share:
                slow.append(f"Historie {dead}/{prior} tot")
            complete = getattr(feats, "creator_history_complete", None)
            v["historie_vollstaendig"] = complete
            if creator_coverage:
                v["historie_umfang"] = creator_coverage
            if cfg.require_complete_history and complete is False:
                if creator_deep in ("offen", "laedt"):
                    pending.append("Historie")
                else:
                    slow.append("Historie unvollständig" + (f" ({creator_coverage})" if creator_coverage else ""))
    else:
        v["historie"] = "ungeprüft"

    if cfg.require_wallet_check and wallet_state != "ungeprüft":
        v["wallets"] = wallet_state
        if wallet_state in ("offen", "laedt"):
            pending.append("Wallets")
        elif wallet_state == "ok" and verbund is not None:
            share = float(verbund.get("share", 0.0))
            unchecked = float(verbund.get("unchecked_share", 0.0))
            v["verbund"] = share
            v["verbund_wallets"] = int(verbund.get("wallets", 0))
            v["verbund_geprueft"] = f"{verbund.get('checked', 0)}/{verbund.get('top', 0)}"
            v["frisch_anteil"] = verbund.get("fresh_share")
            v["verbund_details"] = list(verbund.get("linked", []))[:5]
            if share >= cfg.max_verbund_share:
                slow.append(f"Wallet-Verbund {share * 100:.0f} % in {v['verbund_wallets']} Wallets")
            if unchecked >= cfg.max_verbund_share:
                slow.append(f"{unchecked * 100:.0f} % bei ungeprüften Top-Haltern")
        else:
            slow.append("Wallets nicht geprüft" + (" (RPC-Budget)" if wallet_state == "budget" else ""))
    else:
        v["wallets"] = "ungeprüft"

    if checks_possible and cfg.require_metadata:
        v["metadaten"] = metadata_state
        if metadata_state == "laedt":
            pending.append("Metadaten")
        elif metadata_state in ("fehlt", "fehler"):
            slow.append("keine Metadaten" if metadata_state == "fehlt" else "Metadaten nicht ladbar")
        else:
            soc = int(getattr(feats, "socials_count", 0) or 0)
            img = bool(getattr(feats, "has_image", False))
            v["socials"], v["bild"] = soc, img
            if soc < cfg.min_socials:
                slow.append(f"nur {soc} Social-Links (mindestens {cfg.min_socials})")
            if cfg.require_image and not img:
                slow.append("kein Bild")
    else:
        v["metadaten"] = "ungeprüft"

    hard_ok = not hard
    return FairResult(ok=hard_ok and not slow and not pending, hard_ok=hard_ok, fails=hard + slow, hard_fails=list(hard), pending=pending, values=v)


def fair_line(res: FairResult | None) -> str | None:
    """Kurzzeile für die Nachricht: ✓ mit den geprüften Werten, ✗ mit den verletzten Prinzipien."""
    if res is None or res.values.get("aus"):
        return None
    if res.fails:
        text = "✗ " + "; ".join(res.fails[:3])
    else:
        v = res.values
        parts = [f"Dev {v.get('dev_anteil', 0) * 100:.1f} %", "hält" if not v.get("dev_verkauft") else f"verkauft {v['dev_verkauft'] * 100:.0f} %"]
        if v.get("bundle") is not None:
            parts.append(f"Bundle {v['bundle'] * 100:.0f} %/{v.get('bundle_wallets') if v.get('bundle_wallets') is not None else '?'}")
        if v.get("historie") not in (None, "ungeprüft"):
            parts.append(f"Historie {v['historie']}")
        if v.get("verbund") is not None:
            parts.append(f"Verbund {v['verbund'] * 100:.0f} %")
        if "socials" in v:
            parts.append(f"{v['socials']} Links" + ("+Bild" if v.get("bild") else ""))
        text = "✓ " + " · ".join(parts)
    if res.pending:
        text += " (" + ", ".join(res.pending) + " lädt)"
    return text
