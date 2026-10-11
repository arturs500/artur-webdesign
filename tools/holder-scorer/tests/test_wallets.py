"""Wallet-Prüfung (0.3.7, OQ-034): Top-Halter-Verbund, vollständige Creator-Historie, Reihenfolge Creator vor Profilen."""
from __future__ import annotations

import dataclasses

from holder_scorer.collect import CreatorHistory, ProfileCache, WalletProfile, _creator_history, derive_balances
from holder_scorer.encoding import b58encode
from holder_scorer.fair import FairConfig, fair_line
from holder_scorer.features import compute_features
from holder_scorer.pump import CREATE_EVENT_DISC, derive_bonding_curve
from holder_scorer.scoring import ScoringConfig, hard_fail_reasons, short_flags
from holder_scorer.wallets import holder_verbund, top_holders, verbund_line
from tests.helpers import bonding_curve_bytes, create_event_bytes, fake_tx, key
from tests.test_fair import GOOD_META, TIERS, Feats, _standard_flow, _with_meta, check
from tests.test_live import T0, make_engine

SUPPLY = 1_000_000_000_000_000


# --- holder_verbund ----------------------------------------------------------------------------------------------
def test_verbund_links_dev_source_shared_funders_and_holder_chains():
    balances = {
        "dev": 50_000_000_000_000,  # 5 %: dev addresses never count as top holders
        "a": 40_000_000_000_000,  # funded by the dev
        "b": 30_000_000_000_000,  # same funder as the dev
        "c": 20_000_000_000_000,  # funded by top holder d ...
        "d": 15_000_000_000_000,  # ... so d is linked as well
        "e": 10_000_000_000_000,  # shares an unknown funder with f
        "f": 9_000_000_000_000,
        "g": 8_000_000_000_000,  # exchange payout shared with h: no link
        "h": 7_000_000_000_000,
        "i": 6_000_000_000_000,  # outside the top 8
    }
    profiles = {
        "a": WalletProfile("a", 3, funder="dev"),
        "b": WalletProfile("b", 3, funder="devsrc"),
        "c": WalletProfile("c", 3, funder="d"),
        "d": WalletProfile("d", 40, funder="old"),
        "e": WalletProfile("e", 2, funder="x", is_fresh=True),
        "f": WalletProfile("f", 2, funder="x"),
        "g": WalletProfile("g", 9, funder="binance", funder_busy=True),
        "h": WalletProfile("h", 9, funder="binance", funder_busy=True),
    }
    v = holder_verbund(balances, SUPPLY, profiles, devs={"dev"}, creator_funder="devsrc", top=8)
    assert [x[0] for x in top_holders(balances, {"dev"}, 8)] == ["a", "b", "c", "d", "e", "f", "g", "h"]
    reasons = {x["wallet"]: x["grund"] for x in v.linked}
    assert reasons == {
        "a": "vom Dev finanziert",
        "b": "gleiche Quelle wie der Dev",
        "c": "von einem Top-Halter finanziert",
        "d": "finanzierte einen Top-Halter",
        "e": "gemeinsame Quelle mit 1 Top-Halter(n)",
        "f": "gemeinsame Quelle mit 1 Top-Halter(n)",
    }
    assert v.wallets == 6 and v.share == 0.124 and v.top == 8 and v.checked == 8 and v.unchecked_share == 0.0
    assert v.fresh_share == 0.01
    assert verbund_line(v.to_dict()) == "Verbund 12 % in 6 Wallets (vom Dev finanziert) · geprüft 8/8"


def test_verbund_unknown_is_not_clean_and_exchange_source_of_the_dev_does_not_link():
    balances = {"a": 60_000_000_000_000, "b": 50_000_000_000_000, "c": 1_000_000_000_000}
    # the dev was paid out by an exchange: holders with a payout from the same hot wallet are not the dev's wallets
    profiles = {"a": WalletProfile("a", 9, funder="cex", funder_busy=True), "c": WalletProfile("c", 9, funder="cex", funder_busy=True)}
    v = holder_verbund(balances, SUPPLY, profiles, devs={"dev"}, creator_funder="cex")
    assert v.wallets == 0 and v.share == 0.0
    assert v.checked == 2 and v.unchecked_share == 0.05  # b has no profile
    # a holder that funded the dev hangs on the dev, whatever its own funder
    v2 = holder_verbund(balances, SUPPLY, {"a": WalletProfile("a", 9, funder="cex", funder_busy=True)}, devs={"dev"}, creator_funder="a")
    assert v2.linked[0] == {"wallet": "a", "anteil": 0.06, "grund": "finanzierte den Dev"}


# --- fair gate -----------------------------------------------------------------------------------------------------
def test_fair_gate_wallets_and_history_rules():
    clean = {"share": 0.04, "wallets": 1, "top": 8, "checked": 8, "unchecked_share": 0.0, "fresh_share": 0.0, "linked": [{"wallet": "a", "anteil": 0.04, "grund": "vom Dev finanziert"}]}
    ok = check(Feats(), wallet_state="ok", verbund=clean)
    assert ok.ok and ok.values["verbund"] == 0.04 and ok.values["verbund_geprueft"] == "8/8"
    assert "Verbund 4 %" in fair_line(ok)
    bad = check(Feats(), wallet_state="ok", verbund={**clean, "share": 0.18, "wallets": 3})
    assert bad.hard_ok and not bad.ok and bad.fails == ["Wallet-Verbund 18 % in 3 Wallets"]
    blind = check(Feats(), wallet_state="ok", verbund={**clean, "share": 0.0, "wallets": 0, "unchecked_share": 0.12})
    assert blind.fails == ["12 % bei ungeprüften Top-Haltern"]
    assert check(Feats(), wallet_state="laedt").pending == ["Wallets"] and check(Feats(), wallet_state="offen").pending == ["Wallets"]
    assert check(Feats(), wallet_state="fehler").fails == ["Wallets nicht geprüft"]
    assert check(Feats(), wallet_state="budget").fails == ["Wallets nicht geprüft (RPC-Budget)"]
    assert check(Feats(), wallet_state="ungeprüft").ok
    # Stufe 1 is stricter, Stufe 3 does not wait for wallets at all
    assert not check(Feats(), FairConfig.for_stufe(1), wallet_state="ok", verbund={**clean, "share": 0.06}).ok
    assert check(Feats(), FairConfig.for_stufe(3), wallet_state="laedt").pending == []
    # a failed creator lookup is a missing check, not an empty history
    failed = check(Feats(creator_prior_tokens=None), creator_failed=True)
    assert failed.fails == ["Historie nicht ladbar"] and failed.values["historie"] == "fehler"
    # an incomplete history waits for the deep scan, then blocks with the coverage
    part = Feats(creator_history_complete=False)
    assert check(part, creator_deep="laedt").pending == ["Historie"] and check(part, creator_deep="offen").pending == ["Historie"]
    assert check(part, creator_deep="fertig", creator_coverage="150 von 640 Tx").fails == ["Historie unvollständig (150 von 640 Tx)"]
    assert check(part, FairConfig.for_stufe(3), creator_deep="fehler").ok
    assert "Wallet-Verbund < 10%" in FairConfig.for_stufe(2).summary() and "(vollständig)" in FairConfig.for_stufe(2).summary()


# --- creator history: coverage, deep scan, refresh gap ------------------------------------------------------------
class CreatorRpc:
    def __init__(self, sigs: list[dict], txs: dict, curves: dict):
        self.sigs, self.txs, self.curves = sigs, txs, curves
        self.calls: list[tuple] = []

    def get_signatures(self, address, limit=1000, before=None):
        self.calls.append(("sigs", limit))
        return [dict(s) for s in self.sigs[:limit]]

    def get_transactions(self, signatures):
        self.calls.append(("txs", len(signatures)))
        return {s: self.txs.get(s) for s in signatures}

    def get_multiple_account_data(self, addresses):
        return [self.curves.get(a) for a in addresses]


LAUNCH = int(T0)


def serial_deployer(filler: int = 30, dead: int = 6):
    """A dev wallet whose ``dead`` old launches lie behind ``filler`` newer transactions (sells, transfers)."""
    dev = key()
    sigs, txs, curves = [], {}, {}
    for i in range(filler):
        sig = f"fill{i}"
        txs[sig] = fake_tx(sig, 9000 - i, LAUNCH - 100 - i, dev, [])
        sigs.append({"signature": sig, "slot": 9000 - i, "blockTime": LAUNCH - 100 - i, "err": None})
    for i in range(dead):
        mint = key()
        ts = LAUNCH - 7200 - i * 600
        sig = f"create{i}"
        ev = CREATE_EVENT_DISC + create_event_bytes(f"T{i}", f"T{i}", "", mint, key(), dev, dev, ts)
        txs[sig] = fake_tx(sig, 8000 - i, ts, dev, [ev])
        sigs.append({"signature": sig, "slot": 8000 - i, "blockTime": ts, "err": None})
        # 1 SOL left on the curve, not complete, older than 30 minutes: dead
        curves[derive_bonding_curve(b58encode(mint))] = bonding_curve_bytes(1_000_000_000_000_000, 31_000_000_000, 780_000_000_000_000, 1_000_000_000, SUPPLY, False, dev)
    return b58encode(dev), sigs, txs, curves


def test_creator_history_flags_an_incomplete_scan_and_the_deep_scan_finds_the_series():
    dev, sigs, txs, curves = serial_deployer()
    rpc = CreatorRpc(sigs, txs, curves)
    cache = ProfileCache()
    hist, _, _ = _creator_history(rpc, dev, "newmint", LAUNCH, 30, cache)
    # before 0.3.7: prior 0, source "rpc", sample_capped False – a clean-looking serial deployer
    assert hist.prior_tokens == 0 and not hist.complete and hist.source == "rpc(partial)"
    assert hist.scanned_tx == 30 and hist.ok_tx == 36 and "last 30 of 36" in hist.coverage_note
    deep, _, _ = _creator_history(rpc, dev, "newmint", LAUNCH, 150, cache)
    assert deep.complete and deep.scanned_tx == 36 and deep.prior_tokens == 6 and deep.dead == 6 and deep.source == "rpc"
    # the deep scan only fetched the six unscanned transactions, not the whole page again
    assert rpc.calls[-2:] == [("sigs", 150), ("txs", 6)]
    # a later token of the same dev reads the deep result from the cache
    again, _, _ = _creator_history(rpc, dev, "othermint", LAUNCH + 60, 30, cache)
    assert again.complete and again.prior_tokens == 6


def test_creator_refresh_with_a_gap_reloads_instead_of_claiming_coverage():
    dev, sigs, txs, curves = serial_deployer(filler=5, dead=1)
    rpc = CreatorRpc(sigs, txs, curves)
    cache = ProfileCache()
    first, _, _ = _creator_history(rpc, dev, "m1", LAUNCH, 30, cache)
    assert first.complete and first.prior_tokens == 1
    # 40 new transactions arrive, more than one refresh page of 30: the gap must not be skipped
    new = []
    for i in range(40):
        sig = f"new{i}"
        txs[sig] = fake_tx(sig, 9500 - i, LAUNCH + 500 - i, key(), [])
        new.append({"signature": sig, "slot": 9500 - i, "blockTime": LAUNCH + 500 - i, "err": None})
    rpc.sigs = new + sigs
    rpc.calls.clear()
    second, _, _ = _creator_history(rpc, dev, "m2", LAUNCH + 600, 30, cache)
    assert ("sigs", 1000) in rpc.calls  # full reload
    assert not second.complete and second.ok_tx == 46 and second.scanned_tx == 30


# --- scoring: series rule as documented, slice is not clean ------------------------------------------------------
def _live_feats():
    engine, _ = make_engine(stufe=2, tiers=TIERS)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator)
    state = engine.tokens[b58encode(mint)]
    return compute_features(engine.snapshot(state, T0 + 26), T0 + 26)


def test_five_dead_tokens_are_a_series_even_next_to_live_ones():
    f = dataclasses.replace(_live_feats(), creator_prior_tokens=10, creator_dead=5, creator_graduated=0, creator_young=0)
    cfg = ScoringConfig.early()
    assert any("Serien-Deployer" in r for r in hard_fail_reasons(f, cfg))
    assert any(x.startswith("SERIE") for x in short_flags(f, cfg))
    f4 = dataclasses.replace(f, creator_dead=4)
    assert not any("Serien-Deployer" in r for r in hard_fail_reasons(f4, cfg))


# --- live engine ----------------------------------------------------------------------------------------------------
def _wallet_side(engine_box, history, funder_of, deep=None, record=None, hold_creator=False):
    """Fake side tasks: creator history, metadata, deep scan and wallet profiles built from the engine's own state."""
    held = []

    def side(name, fn, done, delay=0.0, group="rpc"):
        if record is not None:
            record.append(name)
        if name == "creator":
            if hold_creator:
                held.append(done)
            else:
                done((history, WalletProfile("c", 400), "creatorfirstsig"))
        elif name == "metadata":
            done(GOOD_META)
        elif name == "creator_tief":
            done(deep)
        elif name.startswith("wallets"):
            st = next(iter(engine_box[0].tokens.values()))
            devs = engine_box[0]._dev_addresses(st)
            top = top_holders(derive_balances(st.trades), devs, engine_box[0].cfg.wallet_check_top)
            done(([WalletProfile(o, 3, funder=funder_of(st, o)) for o, _ in top], None, []))
        else:
            done(None)

    return side, held


HIST = CreatorHistory(address="c", prior_tokens=2, graduated=1, source="rpc")


def test_go_is_gesperrt_when_the_top_holders_hang_on_the_dev():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: st.creator)
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=side)
    box.append(engine)
    engine.rpc = object()
    engine.cfg.fair.max_verbund_share = 0.005  # the test buyers are small: 8 × 0.08 % of the supply
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GESPERRT"]
    assert "Wallet-Verbund" in alerts[1].text and "Dev solscan.io/account/" in alerts[1].text
    fair = alerts[1].state.fair
    assert fair["values"]["verbund_wallets"] == 8 and fair["values"]["verbund_details"][0]["grund"] == "vom Dev finanziert"


def test_go_passes_when_the_top_holders_are_independent():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o)
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=side)
    box.append(engine)
    engine.rpc = object()
    engine.cfg.fair.max_verbund_share = 0.005
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GO"] and "Verbund 0 %" in alerts[1].text


def test_incomplete_history_gets_one_deep_scan_before_go():
    part = CreatorHistory(address="c", prior_tokens=0, source="rpc(partial)", scanned_tx=30, ok_tx=40, complete=False)
    full = CreatorHistory(address="c", prior_tokens=1, graduated=1, source="rpc", scanned_tx=40, ok_tx=40)
    names: list[str] = []
    box: list = []
    side, _ = _wallet_side(box, part, lambda st, o: "src-" + o, deep=(full, WalletProfile("c", 400), "creatorfirstsig"), record=names)
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=side)
    box.append(engine)
    engine.rpc = object()
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert names.count("creator_tief") == 1 and [a.tier for a in alerts] == ["BLICK", "GO"]
    # the deep scan fails: the slice stays a slice, GO is locked with the coverage as reason
    box2: list = []
    side2, _ = _wallet_side(box2, part, lambda st, o: "src-" + o, deep=None)
    engine2, alerts2 = make_engine(stufe=2, tiers=TIERS, side=side2)
    box2.append(engine2)
    engine2.rpc = object()
    m2, c2 = key(), key()
    _standard_flow(engine2, m2, c2, _with_meta(m2, c2))
    assert [a.tier for a in alerts2] == ["BLICK", "GESPERRT"] and "Historie unvollständig (30 von 40 Tx)" in alerts2[1].text


def test_failed_creator_lookup_locks_go_instead_of_passing():
    box: list = []
    side, _ = _wallet_side(box, None, lambda st, o: "src-" + o)

    def failing(name, fn, done, delay=0.0, group="rpc"):
        if name == "creator":
            done(None)  # RPC error after all retries
        else:
            side(name, fn, done, delay, group)

    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=failing)
    box.append(engine)
    engine.rpc = object()
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GESPERRT"] and "Historie nicht ladbar" in alerts[1].text


def test_early_profiles_wait_for_the_creator_scan():
    names: list[str] = []
    box: list = []
    side, held = _wallet_side(box, HIST, lambda st, o: "src-" + o, record=names, hold_creator=True)
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=side)
    box.append(engine)
    engine.rpc = object()
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    # the creator scan is still out: no early-wallet profiles yet (they would miss the dev's first transaction)
    assert "creator" in names and "profiles" not in names
    held[0]((HIST, WalletProfile("c", 400), "creatorfirstsig"))
    engine.tick(T0 + 28)
    assert "profiles" in names
    state = engine.tokens[b58encode(mint)]
    assert state.creator_first_sig == "creatorfirstsig"


def test_budget_exhaustion_is_not_a_clean_wallet_check():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o)
    engine, alerts = make_engine(stufe=2, tiers=TIERS, side=side)
    box.append(engine)
    engine.rpc = object()
    # the hour's budget runs out right after the creator scan, before the GO candidate's wallet check
    engine.rpc_budget_ok = lambda now=None: not any(st.creator_history for st in engine.tokens.values())
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GESPERRT"] and "Wallets nicht geprüft (RPC-Budget)" in alerts[1].text
