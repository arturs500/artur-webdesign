"""Short messages in a fixed vocabulary, and delivery to Telegram.

The vocabulary ("Kurzsprache") is deliberately tiny so that one glance at a
message tells you what the bot thinks. Every word is documented in
``VOCAB`` and printed by ``holder_scorer legend``.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:  # pragma: no cover
    from .quick import QuickReport

WORDS = {
    "BLICK": ("👀", "Frühalarm im Live-Modus: erste echte Käufer, kein Warnsignal, noch kein volles Urteil"),
    "GO": ("🟢", "kaufbar: kein Warnsignal, genug echte Käufer, gerade Zulauf"),
    "WARTE": ("🟡", "unklar oder Mindestmengen fehlen: nochmal prüfen, nicht kaufen"),
    "FRÜH": ("⏳", "zu jung für ein Urteil (unter dem Mindestalter)"),
    "NEIN": ("⚪", "schwach: Score zu niedrig, aber kein Rug-Muster"),
    "RUG": ("🔴", "Rug-Muster: Bundle, Dev-Dump, Serien-Deployer, Konzentration, Fake-MC oder dünne Liquidität"),
    "TOT": ("⚫", "Handel eingeschlafen"),
    "GRAD": ("🎓", "graduiert, handelt auf PumpSwap: nur Marktzahlen, keine Curve-Analyse"),
    "?": ("❔", "keine Daten oder RPC-Fehler"),
}

FLAGS = {
    "BUNDLE": "Anteil des Supplys, der in den ersten Slots gekauft wurde (Zahl = gekauft %, gehalten %)",
    "DEV-DUMP": "Dev hat praktisch alles verkauft",
    "DEV-RAUS": "Dev hat einen Teil verkauft (Zahl = verkaufter Anteil)",
    "SERIE": "Serien-Deployer: frühere Token / davon graduiert / davon tot",
    "SCHNELL": "Creator hat vor wenigen Minuten schon einen Token gestartet oder startet mehrere pro Stunde",
    "FRISCH": "frühe Wallets, die jünger als 1 Tag sind (frisch / geprüft)",
    "FUNDER": "frühe Wallets vom Creator oder derselben Quelle finanziert",
    "TOP1": "größter Holder-Anteil (Supply oder verkaufter Float)",
    "TOP10": "Anteil der zehn größten Holder",
    "BOTS": "Anteil der Käufe von Bump- oder Wash-Wallets",
    "WASH": "viele Wallets handeln nur hin und her",
    "SELF-PUMP": "Preis steigt ohne neue Käufer",
    "EXIT": "die Erstkäufer haben einen Großteil ihrer Position verkauft",
    "FAKE-MC": "hohe Marktkapitalisierung bei winzigem Handelsvolumen (Zahl = Volumen/MC)",
    "DÜNN": "Liquidität winzig im Verhältnis zur Marktkapitalisierung",
    "STILL": "Sekunden seit dem letzten Trade",
    "NOSOC": "keine echten Social-Links",
    "MAYHEM": "Mayhem-Coin, Schwellen nicht kalibriert",
    "USDC": "Nicht-SOL-Kurve, Schwellen nicht kalibriert",
    "LÜCKE": "Daten unvollständig (Historie gekürzt oder Abfrage fehlgeschlagen)",
    "MINDEST": "Score reicht, aber Mindestmengen für GO fehlen",
}

LINES = {
    "MC": "Marktkapitalisierung in USD und SOL",
    "Vol": "Handelsvolumen gesamt (Kurve) bzw. letzte Stunde (Markt), V/MC = Volumen geteilt durch MC, dahinter die letzten 60 s",
    "Liq": "SOL in der Kurve oder im Pool, Kurve = Fortschritt bis zur Graduation",
    "Hold": "Holder jetzt und Veränderung in den letzten 60 s",
    "Buys": "Käufe / Verkäufe der letzten 120 s (organisch: ohne Dev, Bundle, Bots) und Netto-SOL-Fluss",
    "Dev": "Dev-Kaufanteil und ob er hält, dahinter Bundle-Anteil",
    "Crea": "Creator: frühere Token, graduiert, tot",
    "Soc": "Social-Links (X = Twitter, TG = Telegram, WWW = Website) und Bot-Anteil der Käufe",
}


def fmt_usd(x: float | None) -> str:
    if x is None:
        return "?"
    if x >= 1_000_000:
        return f"{x / 1_000_000:.2f}M$"
    if x >= 10_000:
        return f"{x / 1000:.0f}k$"
    if x >= 1_000:
        return f"{x / 1000:.1f}k$"
    return f"{x:.0f}$"


def fmt_sol(x: float | None, digits: int = 1) -> str:
    return "?" if x is None else f"{x:.{digits}f} SOL"


def fmt_pct(x: float | None, digits: int = 0) -> str:
    return "?" if x is None else f"{x * 100:.{digits}f}%"


def fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    s = int(max(0, seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def format_short(r: "QuickReport", suffix: str | None = None, link: bool = False) -> str:
    """Ten short lines: verdict, numbers stacked, flags last (plus an optional link line)."""
    emoji = WORDS.get(r.word, ("❔", ""))[0]
    label = r.symbol or (r.name[:12] if r.name else r.mint[:6])
    score = f" {r.score:.0f}" if r.score is not None else ""
    head = f"{emoji} {r.word}{score} · {label} · {fmt_age(r.age_s)}"
    if suffix:
        head += f" · {suffix}"
    lines = [head]
    mc = fmt_usd(r.mc_usd)
    if r.mc_sol is not None:
        mc += f" · {fmt_sol(r.mc_sol)}"
    lines.append(f"MC   {mc}")
    vol = fmt_usd(r.volume_usd)
    if r.turnover is not None:
        vol += f" · V/MC {r.turnover:.2f}"
    if r.volume_60s_sol is not None:
        vol += f" · 60s {fmt_sol(r.volume_60s_sol)}"
    lines.append(f"Vol  {vol}")
    liq = fmt_sol(r.liquidity_sol) if r.liquidity_sol is not None else fmt_usd(r.liquidity_usd)
    if r.liq_to_mc is not None:
        liq += f" · L/MC {r.liq_to_mc:.2f}"
    if r.progress is not None:
        liq += f" · Kurve {fmt_pct(r.progress)}"
    lines.append(f"Liq  {liq}")
    hold = "?" if r.holders is None else str(r.holders)
    if r.holders_delta_60s is not None:
        hold += f" · {r.holders_delta_60s:+d} in 60s"
    lines.append(f"Hold {hold}")
    buys = f"{r.buys if r.buys is not None else '?'} / {r.sells if r.sells is not None else '?'}"
    if r.net_flow_sol is not None:
        buys += f" · Netto {r.net_flow_sol:+.1f} SOL"
    lines.append(f"Buys {buys}")
    if r.dev_share is not None:
        dev = fmt_pct(r.dev_share, 1)
        if r.dev_sold is not None:
            dev += " hält" if r.dev_sold < 0.05 else f" ({fmt_pct(r.dev_sold)} verkauft)"
    else:
        dev = "?"
    if r.bundle_share is not None:
        dev += f" · Bundle {fmt_pct(r.bundle_share)}"
    lines.append(f"Dev  {dev}")
    if r.creator_prior is not None:
        crea = f"{r.creator_prior} Tok · {r.creator_graduated or 0} grad · {r.creator_dead or 0} tot"
    else:
        crea = "?"
    lines.append(f"Crea {crea}")
    soc = r.socials_text or "?"
    if r.bots_share is not None:
        soc += f" · Bots {fmt_pct(r.bots_share)}"
    lines.append(f"Soc  {soc}")
    lines.append("⚠️   " + (" · ".join(r.flags) if r.flags else "–"))
    if link:
        lines.append(f"pump.fun/coin/{r.mint}")
    return "\n".join(lines)


def format_legend() -> str:
    out = ["Urteile:"]
    for word, (emoji, meaning) in WORDS.items():
        out.append(f"  {emoji} {word:<6} {meaning}")
    out.append("\nZeilen:")
    for key, meaning in LINES.items():
        out.append(f"  {key:<5} {meaning}")
    out.append("\nWarnungen (letzte Zeile):")
    for key, meaning in FLAGS.items():
        out.append(f"  {key:<10} {meaning}")
    return "\n".join(out)


def send_telegram(text: str, token: str | None = None, chat_id: str | None = None, timeout: float = 6.0) -> bool:
    """Send a plain-text message through the Telegram Bot API. Returns True on success."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=timeout,
        )
        return resp.status_code == 200 and bool((resp.json() or {}).get("ok"))
    except (requests.RequestException, ValueError):
        return False


def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
