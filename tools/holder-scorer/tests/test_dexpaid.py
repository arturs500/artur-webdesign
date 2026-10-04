"""DexScreener-Bezahlsignale (0.3.3, OQ-030): Beobachter mit Fake-HTTP, Budget, Schnappschüsse, Report, CLI."""
from __future__ import annotations

import json

from holder_scorer.cli import build_parser, cmd_dex
from holder_scorer.dexpaid import BASE_URL, FEED_BOOSTS, FEED_PROFILES, TOKENS, DexWatcher, best_pair, boost_bucket, dex_report, follower_return

M1, M2, M3 = "A" * 44, "B" * 44, "C" * 44


def pair(mint: str, price: float, liq: float = 50_000.0, chain: str = "solana", boosts: int | None = None) -> dict:
    p = {
        "chainId": chain, "dexId": "pumpswap", "url": "https://dexscreener.com/solana/x", "pairAddress": "P" + mint[1:],
        "baseToken": {"address": mint, "name": "n", "symbol": "s"}, "quoteToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL"},
        "priceNative": str(price / 150), "priceUsd": str(price), "txns": {"m5": {"buys": 12, "sells": 4}}, "volume": {"m5": 1000.0, "h1": 9000.0, "h24": 50000.0},
        "liquidity": {"usd": liq, "base": 1, "quote": 1}, "fdv": 1_000_000, "marketCap": 900_000, "pairCreatedAt": 1_800_000_000_000,
    }
    if boosts is not None:
        p["boosts"] = {"active": boosts}
    return p


class FakeApi:
    """Antwortet wie der Referenz-Spiegel: Boosts/Profile als Listen, Tokens als {"pairs": [...]}. Preise je Phase steuerbar."""

    def __init__(self):
        self.boosts: list[dict] = []
        self.profiles: list[dict] = []
        self.prices: dict[str, float] = {}
        self.calls: list[str] = []
        self.status = 200

    def __call__(self, url: str):
        self.calls.append(url)
        assert url.startswith(BASE_URL)
        path = url[len(BASE_URL):]
        if self.status != 200:
            return self.status, None
        if path == FEED_BOOSTS:
            return 200, list(self.boosts)
        if path == FEED_PROFILES:
            return 200, list(self.profiles)
        if path.startswith(TOKENS):
            mints = path[len(TOKENS):].split(",")
            assert len(mints) <= 30
            pairs = []
            for m in mints:
                if m in self.prices:
                    pairs.append(pair(m, self.prices[m], boosts=10))
                    pairs.append(pair(m, self.prices[m] * 1.5, liq=10.0))  # dünneres Zweitpaar: wird nicht genommen
            return 200, {"schemaVersion": "1.0.0", "pairs": pairs}
        return 404, None


def boost(mint: str, amount: int, total: int, chain: str = "solana") -> dict:
    return {"url": "https://dexscreener.com/solana/" + mint, "chainId": chain, "tokenAddress": mint, "amount": amount, "totalAmount": total, "icon": "i", "description": "d" * 30, "links": [{"type": "twitter", "url": "x"}]}


def test_helpers_bucket_pair_and_return():
    assert [boost_bucket(x) for x in (10, 30, 50, 100, 500, 3000, None)] == ["10", "30", "50", "100", "500+", "500+", "10"]
    pairs = [pair(M1, 1.0, liq=100.0), pair(M1, 2.0, liq=900.0), pair(M1, 3.0, chain="base"), pair(M2, 4.0)]
    assert best_pair(pairs, M1, "solana")["priceUsd"] == "2.0" and best_pair(pairs, M3, "solana") is None
    assert abs(follower_return(1.0, 1.0, 50) - (0.995**2 - 1)) < 1e-12 and follower_return(None, 1.0, 50) is None and follower_return(1.0, 2.0, 0) == 1.0


def test_watcher_records_events_snapshots_and_respects_budget(tmp_path):
    api = FakeApi()
    api.boosts = [boost(M1, 10, 10), boost(M2, 100, 100), boost(M3, 50, 50, chain="base")]
    api.profiles = [{"url": "u", "chainId": "solana", "tokenAddress": M2, "description": "p", "links": []}]
    api.prices = {M1: 1.0, M2: 2.0}
    out = tmp_path / "dex.jsonl"
    w = DexWatcher(out_path=str(out), fetch=api, poll_s=60.0, horizons=(300.0,))
    t0 = 1_800_000_000.0
    w.tick(t0)
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    kinds = [r["typ"] for r in rows]
    assert kinds.count("boost") == 2 and kinds.count("profil") == 1 and kinds.count("preis") == 3  # Base-Boost ignoriert
    assert {r["mint"] for r in rows if r["typ"] == "boost"} == {M1, M2} and [r["paket"] for r in rows if r["typ"] == "boost"] == ["10", "100"]
    first = [r for r in rows if r["typ"] == "preis"]
    assert all(r["geplant_nach_s"] == 0.0 for r in first) and {r["preis_usd"] for r in first} == {1.0, 2.0} and all(r["boosts_aktiv"] == 10 for r in first)
    assert len(w.due) == 3 and w.stats["anfragen"] == 3  # Boosts, Profile, ein Token-Aufruf für alle drei Mints
    # gleicher Feed-Stand: keine neuen Ereignisse; neuer Boost-Kauf (totalAmount steigt) zählt erneut
    api.boosts[0] = boost(M1, 30, 40)
    w.tick(t0 + 60)
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert [r["typ"] for r in rows].count("boost") == 3 and w.stats["boosts"] == 3 and w.stats["profile"] == 1
    # +5 min: Folgepreise, M1 verdoppelt, M2 fällt, M3 (Profil unbekannt) fehlt
    api.prices = {M1: 2.0, M2: 1.0}
    w.tick(t0 + 301)
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    later = [r for r in rows if r["typ"] == "preis" and r["geplant_nach_s"] == 300.0]
    assert len(later) == 3 and sorted(r["preis_usd"] for r in later) == [1.0, 1.0, 2.0] and all(r["verzug_s"] <= 1.0 for r in later)
    # Budget: nach 429 eine Minute Pause, keine weiteren Anfragen in dieser Minute
    api.status = 429
    w.tick(t0 + 420)
    n = w.stats["anfragen"]
    w.tick(t0 + 430)
    assert w.stats["limit"] == 1 and w.stats["anfragen"] == n
    api.status = 200
    w.tick(t0 + 500)
    assert w.stats["anfragen"] > n and "Boost-Käufe" in w.status_line()
    # Report: Rendite je Gruppe
    text, report = dex_report(str(out), fee_bps=50, horizons=(300.0,))
    alle = report["summary"]["alle|300"]
    # vier Ereignisse: Boost M1 (1,0 → 2,0), Boost M2 (2,0 → 1,0), Profil M2 (2,0 → 1,0), zweiter Boost M1 (1,0 → 2,0)
    assert alle["n"] == 4 and alle["treffer"] == 0.5
    assert report["summary"]["boost=10|300"]["n"] == 1 and report["summary"]["boost=10|300"]["mean"] > 0.9
    assert "typ=profil|300" in report["summary"] and "EXP004" in text
    args = build_parser().parse_args(["dex", "report", str(out), "--gebuehr-bps", "25", "--json", str(tmp_path / "d.json")])
    assert args.func is cmd_dex and cmd_dex(args) == 0 and (tmp_path / "d.json").exists()
    assert build_parser().parse_args(["dex", "beobachten", "--out", "x.jsonl", "--dauer", "10"]).intervall == 60.0


def test_report_joins_our_alert_records(tmp_path):
    out = tmp_path / "dex.jsonl"
    t = 1_800_000_000.0
    rows = [
        {"typ": "boost", "t": t + 1800, "mint": M1, "paket": "10", "ereignis": "e1"},
        {"typ": "preis", "t": t + 1800, "mint": M1, "ereignis": "e1", "geplant_nach_s": 0.0, "preis_usd": 1.0},
        {"typ": "preis", "t": t + 2100, "mint": M1, "ereignis": "e1", "geplant_nach_s": 300.0, "preis_usd": 1.2},
        {"typ": "profil", "t": t + 600, "mint": M2, "ereignis": "e2"},
        {"typ": "preis", "t": t + 600, "mint": M2, "ereignis": "e2", "geplant_nach_s": 0.0, "fehlt": True},
    ]
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    rec = tmp_path / "live.jsonl"
    rec.write_text("\n".join(json.dumps(r) for r in [{"mint": M1, "tier": "GO", "launch_received_at": t, "slot": 1, "alert_at": t + 30}, {"mint": M3, "tier": "BLICK", "launch_received_at": t, "slot": 1, "alert_at": t + 20}]) + "\n", encoding="utf-8")
    text, report = dex_report(str(out), records_path=str(rec), fee_bps=0, horizons=(300.0,))
    assert report["ohne_startpreis"] == 1 and report["records"] == {"alarm_coins": 2, "davon_mit_bezahlsignal": 1, "median_minuten_nach_launch": 30.0, "boosts": 1, "profile": 0}
    assert abs(report["summary"]["alle|300"]["mean"] - 0.2) < 1e-9 and "Eigene Alarm-Coins: 2" in text
