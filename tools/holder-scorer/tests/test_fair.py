"""Fairness-Gate (0.3.4, OQ-031): die Prinzipien aus docs/fair_launch.md als Bedingung für BLICK und GO, GESPERRT als Aufzeichnung."""
from __future__ import annotations

from holder_scorer.calibrate import alert_record_extra
from holder_scorer.cli import build_parser
from holder_scorer.collect import CreatorHistory, WalletProfile
from holder_scorer.encoding import b58encode
from holder_scorer.fair import FairConfig, FairResult, fair_check, fair_line
from holder_scorer.live import LiveConfig
from tests.helpers import key
from tests.test_live import T0, feed_buyers, launch_msg, make_engine, trade_logs

TIERS = ("BLICK", "GO", "WIDERRUF", "RUG", "GESPERRT")


class Feats:
    """Nur die Merkmale, die das Gate liest."""

    def __init__(self, **kw):
        base = dict(dev_buy_share=0.02, dev_holds_share=0.02, dev_sold_share=0.0, creation_window_share=0.0, creation_slot_buyers=1, hidden_float_share=0.0,
                    wash_share=0.0, bot_buy_share=0.0, unique_traders=10, creator_prior_tokens=2, creator_dead=0, creator_graduated=1, creator_is_fresh=False,
                    socials_count=3, has_image=True)
        base.update(kw)
        self.__dict__.update(base)


def check(feats, cfg=None, **kw):
    args = dict(bundle_limit=0.10, copycat=False, creator_done=True, creator_possible=True, metadata_state="ok", checks_possible=True)
    args.update(kw)
    return fair_check(feats, cfg or FairConfig.for_stufe(2), **args)


def test_fair_check_rules_and_pending():
    ok = check(Feats())
    assert ok.ok and ok.hard_ok and ok.fails == [] and ok.pending == [] and ok.values["historie"] == "2 Tok/1 grad/0 tot"
    assert fair_line(ok) == "✓ Dev 2.0 % · hält · Bundle 0 %/1 · Historie 2 Tok/1 grad/0 tot · 3 Links+Bild"
    r = check(Feats(dev_buy_share=0.08, dev_holds_share=0.08))
    assert not r.hard_ok and r.fails == ["Dev-Anteil 8.0 % über 7 %"]
    assert check(Feats(dev_sold_share=0.1)).fails == ["Dev verkauft 10 %"]
    assert check(Feats(creation_window_share=0.12)).fails == ["Bundle 12 % ab 10 %"]
    assert check(Feats(creation_slot_buyers=6)).fails == ["6 Wallets im Create-Block (höchstens 5)"]
    assert check(Feats(), copycat=True).fails == ["Kopie eines Launches der letzten Stunde"]
    assert check(Feats(hidden_float_share=0.03)).fails == ["unsichtbarer Float 3.0 %"]
    assert check(Feats(wash_share=0.3)).fails == ["Wash 30 %"] and check(Feats(bot_buy_share=0.4)).fails == ["Bots 40 %"]
    slow = check(Feats(creator_is_fresh=True, creator_prior_tokens=4, creator_dead=3, socials_count=1, has_image=False))
    assert slow.hard_ok and not slow.ok and slow.fails == ["frisches Dev-Wallet", "Historie 3/4 tot", "nur 1 Social-Links (mindestens 2)", "kein Bild"]
    assert fair_line(slow).startswith("✗ frisches Dev-Wallet; Historie 3/4 tot; nur 1 Social-Links")
    pend = check(Feats(), creator_done=False, metadata_state="laedt")
    assert pend.hard_ok and not pend.ok and pend.fails == [] and pend.pending == ["Historie", "Metadaten"] and fair_line(pend).endswith("(Historie, Metadaten lädt)")
    assert check(Feats(), metadata_state="fehlt").fails == ["keine Metadaten"] and check(Feats(), metadata_state="fehler").fails == ["Metadaten nicht ladbar"]
    # ohne RPC/Nebenabfragen bleiben Historie und Metadaten ungeprüft, aber nicht blockierend
    offline = check(Feats(socials_count=0, has_image=False), creator_possible=False, checks_possible=False)
    assert offline.ok and offline.values["historie"] == "ungeprüft" and offline.values["metadaten"] == "ungeprüft"
    off = fair_check(Feats(dev_buy_share=0.5), FairConfig(enabled=False), bundle_limit=0.1, copycat=True, creator_done=False, creator_possible=True, metadata_state="fehlt", checks_possible=True)
    assert off.ok and fair_line(off) is None and fair_line(None) is None
    s3 = FairConfig.for_stufe(3)
    assert not s3.block_copycat and not s3.require_metadata and s3.max_dev_share == 0.10 and "Kopie" not in s3.summary()
    assert FairConfig.for_stufe(1).max_creation_buyers == 3 and "Historie Pflicht" in FairConfig.for_stufe(1).summary()
    assert "GESPERRT" in LiveConfig.for_stufe(2)[0].tiers and LiveConfig.for_stufe(1)[0].fair.max_dev_share == 0.05


def _standard_flow(engine, mint, creator, msg=None):
    engine.on_launch(msg or launch_msg(mint, creator), now=T0)
    engine.on_logs(b58encode(mint), 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.5, sol=0.12)
    engine.tick(T0 + 12)
    feed_buyers(engine, mint, creator, 10, T0 + 14, 1.0)
    engine.tick(T0 + 26)


def test_fair_go_and_copycat_gets_gesperrt_instead_of_go():
    engine, alerts = make_engine(stufe=2, tiers=TIERS)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]
    go = alerts[1]
    assert "Fair ✓ Dev 2.0 % · hält · Bundle 0 %/3" in go.text  # drei fremde Wallets im Create-Fenster (Slot 5000–5004), unter der Grenze 5 and go.state.fair["ok"] is True
    rec = alert_record_extra(go, 2, "abc", "0.3.4", engine.cfg, engine.scoring)
    assert rec["fair"]["ok"] and rec["fair"]["values"]["dev_anteil"] == 0.02
    # zweiter Launch mit gleichem Namen: Kopie → kein BLICK, statt GO einmal GESPERRT
    mint2, creator2 = key(), key()
    _standard_flow(engine, mint2, creator2)
    tiers = [a.tier for a in alerts]
    assert tiers == ["BLICK", "GO", "GESPERRT"] and engine.stats["gesperrt"] == 1
    sperre = alerts[2]
    assert sperre.state.mint == b58encode(mint2) and "statt GO · Kopie eines Launches der letzten Stunde" in sperre.text and "Fair ✗ Kopie" in sperre.text
    engine.tick(T0 + 31)
    assert [a.tier for a in alerts] == ["BLICK", "GO", "GESPERRT"]  # nur einmal je Token


def test_dev_sale_after_blick_gives_widerruf_and_blocks_go():
    engine, alerts = make_engine(stufe=2, tiers=TIERS)
    mint, creator = key(), key()
    engine.on_launch(launch_msg(mint, creator), now=T0)
    engine.on_logs(b58encode(mint), 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.5, sol=0.12)
    engine.tick(T0 + 12)
    assert [a.tier for a in alerts] == ["BLICK"]
    # der Dev verkauft 10 % seines Kaufs: unter der DEV-RAUS-Schwelle des Scores (20 %), aber ein Bruch des Prinzips
    engine.on_logs(b58encode(mint), 5100, "devsell", None, trade_logs(mint, creator, 0.05, 2_000_000.0, False, int(T0 + 14), creator), now=T0 + 14)
    engine.tick(T0 + 15)
    assert [a.tier for a in alerts] == ["BLICK", "WIDERRUF"] and "Dev verkauft 10 %" in alerts[1].text
    feed_buyers(engine, mint, creator, 10, T0 + 16, 1.0)
    engine.tick(T0 + 27)
    tiers = [a.tier for a in alerts]
    assert "GO" not in tiers and tiers[-1] == "GESPERRT" and "Dev verkauft 10 %" in alerts[-1].text
    big = plan_dev_share(0.08)
    assert "Dev-Anteil 8.0 % über 7 %" in big


def plan_dev_share(share: float) -> list[str]:
    engine, _ = make_engine(stufe=2, tiers=TIERS)
    mint, creator = key(), key()
    msg = launch_msg(mint, creator, initial_buy_tokens=share * 1_000_000_000, sol=2.5)
    engine.on_launch(msg, now=T0)
    engine.on_logs(b58encode(mint), 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
    feed_buyers(engine, mint, creator, 6, T0 + 3, 1.5, sol=0.12)
    engine.tick(T0 + 12)
    return engine.tokens[b58encode(mint)].fair["fails"]


def _side_factory(history=None, profile=None, metadata=None, skip_metadata=False):
    def side(name, fn, done, delay=0.0, group="rpc"):
        if name == "creator":
            done((history, profile, None))
        elif name == "metadata":
            if not skip_metadata:
                done(metadata)
        else:
            done(None)

    return side


def _with_meta(mint, creator):
    msg = launch_msg(mint, creator)
    msg["uri"] = "ipfs://meta"
    return msg


GOOD_META = {"image": "https://img/x.png", "twitter": "https://x.com/abc", "telegram": "https://t.me/abc", "description": "d" * 50}


def test_go_waits_for_history_and_metadata_and_rejects_fresh_dev_or_missing_socials():
    hist = CreatorHistory(address="c", prior_tokens=2, graduated=1, source="rpc")
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=_side_factory(hist, WalletProfile(address="c", tx_count=400), GOOD_META))
    engine.rpc = object()
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GO"]
    assert "Historie 2 Tok/1 grad/0 tot" in alerts[1].text and "2 Links+Bild" in alerts[1].text
    # frisches Dev-Wallet: GESPERRT statt GO
    engine2, alerts2 = make_engine(stufe=2, tiers=TIERS, side=_side_factory(hist, WalletProfile(address="c", tx_count=2, is_fresh=True), GOOD_META))
    engine2.rpc = object()
    m2, c2 = key(), key()
    _standard_flow(engine2, m2, c2, _with_meta(m2, c2))
    assert [a.tier for a in alerts2] == ["BLICK", "GESPERRT"] and "frisches Dev-Wallet" in alerts2[1].text
    # Metadaten ohne Socials: GESPERRT
    engine3, alerts3 = make_engine(stufe=2, tiers=TIERS, side=_side_factory(hist, WalletProfile(address="c", tx_count=400), {"image": "https://img/x.png"}))
    engine3.rpc = object()
    m3, c3 = key(), key()
    _standard_flow(engine3, m3, c3, _with_meta(m3, c3))
    assert [a.tier for a in alerts3] == ["BLICK", "GESPERRT"] and "nur 0 Social-Links (mindestens 2)" in alerts3[1].text
    # Metadaten laden noch: kein GO, aber auch kein GESPERRT (nichts Endgültiges)
    engine4, alerts4 = make_engine(stufe=2, tiers=TIERS, side=_side_factory(hist, WalletProfile(address="c", tx_count=400), None, skip_metadata=True))
    engine4.rpc = object()
    m4, c4 = key(), key()
    _standard_flow(engine4, m4, c4, _with_meta(m4, c4))
    st4 = engine4.tokens[b58encode(m4)]
    assert [a.tier for a in alerts4] == ["BLICK"] and st4.fair["pending"] == ["Metadaten"] and engine4.stats.get("gesperrt", 0) == 0
    assert "(Metadaten lädt)" in alerts4[0].text
    # Stufe 3 verlangt weder Historie noch Metadaten
    engine5, alerts5 = make_engine(stufe=3, tiers=TIERS, side=_side_factory(hist, WalletProfile(address="c", tx_count=2, is_fresh=True), None, skip_metadata=True))
    engine5.rpc = object()
    m5, c5 = key(), key()
    _standard_flow(engine5, m5, c5, _with_meta(m5, c5))
    assert "GO" in [a.tier for a in alerts5]


def test_cli_fair_flags_parse():
    args = build_parser().parse_args(["live", "--no-fair", "--fair-dev-max", "0.04", "--fair-socials", "3", "--fair-ohne-historie"])
    assert args.no_fair and args.fair_dev_max == 0.04 and args.fair_socials == 3 and args.fair_ohne_historie
    assert isinstance(FairResult(True, True), FairResult)
