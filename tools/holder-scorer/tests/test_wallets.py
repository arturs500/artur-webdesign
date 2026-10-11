"""Wallet-Prüfung (0.3.7, OQ-034): Top-Halter-Verbund, vollständige Creator-Historie, Reihenfolge Creator vor Profilen."""
from __future__ import annotations

import dataclasses

from holder_scorer.cli import apply_fair_args, build_parser
from holder_scorer.collect import CreatorHistory, ProfileCache, WalletProfile, _creator_history, _early_wallets, derive_balances
from holder_scorer.encoding import b58encode
from holder_scorer.fair import FairConfig, fair_line
from holder_scorer.features import compute_features
from holder_scorer.pump import CREATE_EVENT_DISC, derive_bonding_curve
from holder_scorer.rpc import RpcError
from holder_scorer.scoring import ScoringConfig, hard_fail_reasons, short_flags
from holder_scorer.wallets import holder_verbund, top_holders, verbund_line
from tests.helpers import bonding_curve_bytes, create_event_bytes, fake_tx, key
from tests.test_fair import GOOD_META, TIERS, Feats, _standard_flow, _with_meta, check
from tests.test_live import T0, feed_buyers, make_engine

SUPPLY = 1_000_000_000_000_000


# --- holder_verbund ----------------------------------------------------------------------------------------------
def test_verbund_links_dev_source_shared_funders_and_holder_chains():
    balances = {
        "dev": 50_000_000_000_000,  # 5 %: dev addresses never count as top holders
        "a": 40_000_000_000_000,  # funded by the dev
        "b": 30_000_000_000_000,  # same funder as the dev (checked: not an exchange)
        "c": 20_000_000_000_000,  # funded by top holder d ...
        "d": 15_000_000_000_000,  # ... so d is linked as well
        "e": 10_000_000_000_000,  # shares a checked non-exchange funder with f
        "f": 9_000_000_000_000,
        "g": 8_000_000_000_000,  # exchange payout shared with h: no link
        "h": 7_000_000_000_000,
        "i": 6_000_000_000_000,  # outside the top 8
    }
    profiles = {
        "a": WalletProfile("a", 3, funder="dev"),
        "b": WalletProfile("b", 3, funder="devsrc", funder_busy=False),
        "c": WalletProfile("c", 3, funder="d"),
        "d": WalletProfile("d", 40, funder="old"),
        "e": WalletProfile("e", 2, funder="x", funder_busy=False, is_fresh=True),
        "f": WalletProfile("f", 2, funder="x", funder_busy=False),
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


def test_verbund_unknown_is_not_clean():
    balances = {"a": 60_000_000_000_000, "b": 50_000_000_000_000, "c": 10_000_000_000_000, "d": 10_000_000_000_000}
    # the dev was paid out by an exchange: holders with a payout from the same hot wallet are not the dev's wallets
    profiles = {"a": WalletProfile("a", 9, funder="cex", funder_busy=True), "c": WalletProfile("c", 9, funder="cex", funder_busy=True)}
    v = holder_verbund(balances, SUPPLY, profiles, devs={"dev"}, creator_funder="cex")
    assert v.wallets == 0 and v.share == 0.0
    assert v.checked == 2 and v.unchecked_share == 0.06  # b and d have no profile
    # a holder that funded the dev hangs on the dev, whatever its own funder
    v2 = holder_verbund(balances, SUPPLY, {"a": WalletProfile("a", 9, funder="cex", funder_busy=True)}, devs={"dev"}, creator_funder="a")
    assert v2.linked[0] == {"wallet": "a", "anteil": 0.06, "grund": "finanzierte den Dev"}
    # the exchange check of a shared source did not run or failed (None): neither linked nor clean
    unsure = {
        "a": WalletProfile("a", 9, funder="src"),  # shares the dev's source, check missing
        "b": WalletProfile("b", 9, funder="y"),  # shares y with c, check missing
        "c": WalletProfile("c", 9, funder="y"),
        "d": WalletProfile("d", 9, funder_unknown=True),  # first transaction never loaded
    }
    v3 = holder_verbund(balances, SUPPLY, unsure, devs={"dev"}, creator_funder="src")
    assert v3.wallets == 0 and v3.checked == 0 and v3.unchecked_share == 0.13
    # unique funders need no exchange check: a holder with its own source is checked and clean
    v4 = holder_verbund(balances, SUPPLY, {"a": WalletProfile("a", 9, funder="only-a")}, devs={"dev"}, creator_funder="src")
    assert v4.checked == 1 and v4.unchecked_share == 0.07


# --- fair gate -----------------------------------------------------------------------------------------------------
CLEAN = {"share": 0.04, "wallets": 1, "top": 8, "checked": 8, "unchecked_share": 0.0, "fresh_share": 0.0, "linked": [{"wallet": "a", "anteil": 0.04, "grund": "vom Dev finanziert"}]}


def test_fair_gate_wallet_rules():
    ok = check(Feats(), wallet_state="ok", verbund=CLEAN)
    assert ok.ok and ok.values["verbund"] == 0.04 and ok.values["verbund_geprueft"] == "8/8" and "Verbund 4 %" in fair_line(ok)
    bad = check(Feats(), wallet_state="ok", verbund={**CLEAN, "share": 0.18, "wallets": 3})
    assert bad.hard_ok and not bad.ok and bad.fails == ["Wallet-Verbund 18 % in 3 Wallets"]
    # unknown is not clean: linked plus unchecked counts against the same limit, final only after the last round
    blind = {**CLEAN, "share": 0.06, "wallets": 2, "unchecked_share": 0.05}
    assert check(Feats(), wallet_state="ok", verbund=blind, wallet_final=True).fails == ["Wallet-Verbund 6 % (+5 % ungeprüft)"]
    assert check(Feats(), wallet_state="ok", verbund=blind, wallet_final=False).pending == ["Wallets"]
    assert check(Feats(), wallet_state="ok", verbund={**CLEAN, "unchecked_share": 0.05}, wallet_final=True).ok  # 4 + 5 < 10
    # a running, due, or budget-blocked round is pending, never a verdict; a failed last round is a breach
    for st in ("laedt", "offen", "budget"):
        r = check(Feats(), wallet_state=st)
        assert r.pending == ["Wallets"] and r.fails == [], st
    assert check(Feats(), wallet_state="fehler", wallet_final=True).fails == ["Wallets nicht geprüft"]
    assert check(Feats(), wallet_state="fehler", wallet_final=False).pending == ["Wallets"]
    assert check(Feats(), wallet_state="ungeprüft").ok
    # Stufe 1 is stricter; Stufe 3 checks without waiting: pending states pass, a present result still blocks
    assert not check(Feats(), FairConfig.for_stufe(1), wallet_state="ok", verbund={**CLEAN, "share": 0.06}).ok
    s3 = FairConfig.for_stufe(3)
    assert s3.require_wallet_check and not s3.wait_for_wallets and s3.max_verbund_share == 0.20
    assert check(Feats(), s3, wallet_state="laedt").ok and check(Feats(), s3, wallet_state="budget").ok
    assert check(Feats(), s3, wallet_state="ok", verbund={**CLEAN, "share": 0.25, "wallets": 4}).fails == ["Wallet-Verbund 25 % in 4 Wallets"]
    assert "Wallet-Verbund < 10%" in FairConfig.for_stufe(2).summary() and "(ohne Warten)" in s3.summary()


def test_fair_gate_history_rules():
    # a failed creator lookup is a missing check, not an empty history
    failed = check(Feats(creator_prior_tokens=None), creator_failed=True)
    assert failed.fails == ["Historie nicht ladbar"] and failed.values["historie"] == "fehler"
    # an incomplete history waits for the deep scan (also while it waits for budget), then blocks with the coverage
    part = Feats(creator_history_complete=False)
    for deep in ("offen", "laedt", "budget"):
        assert check(part, creator_deep=deep).pending == ["Historie"], deep
    assert check(part, creator_deep="fertig", creator_coverage="150 von 640 Tx").fails == ["Historie unvollständig (150 von 640 Tx)"]
    assert check(part, FairConfig.for_stufe(3), creator_deep="fertig").ok
    assert "(vollständig)" in FairConfig.for_stufe(2).summary()


def test_cli_wallet_flags_map_onto_the_gate():
    args = build_parser().parse_args(["live", "--fair-ohne-wallets", "--fair-verbund-max", "0.05", "--fair-ohne-historie"])
    fair = FairConfig.for_stufe(2)
    apply_fair_args(fair, args)
    assert fair.enabled and not fair.require_wallet_check and fair.max_verbund_share == 0.05
    assert not fair.require_creator_check and not fair.require_complete_history
    plain = FairConfig.for_stufe(2)
    apply_fair_args(plain, build_parser().parse_args(["live"]))
    assert plain == FairConfig.for_stufe(2)


# --- creator history: coverage, deep scan, refresh gap, dropped transactions ---------------------------------------
class CreatorRpc:
    def __init__(self, sigs: list[dict], txs: dict, curves: dict, drop: set[str] | None = None, drop_once: bool = True):
        self.sigs, self.txs, self.curves = sigs, txs, curves
        self.drop = set(drop or ())  # signatures the transport "loses" (None in the batch result)
        self.drop_once = drop_once
        self.calls: list[tuple] = []

    def get_signatures(self, address, limit=1000, before=None):
        self.calls.append(("sigs", limit))
        return [dict(s) for s in self.sigs[:limit]]

    def get_transactions(self, signatures):
        self.calls.append(("txs", len(signatures)))
        out = {s: (None if s in self.drop else self.txs.get(s)) for s in signatures}
        if self.drop_once:
            self.drop.clear()
        return out

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


def test_creator_refresh_with_a_gap_reloads_and_keeps_the_known_launches():
    dev, sigs, txs, curves = serial_deployer(filler=5, dead=1)
    rpc = CreatorRpc(sigs, txs, curves)
    cache = ProfileCache()
    first, _, _ = _creator_history(rpc, dev, "m1", LAUNCH, 30, cache)
    assert first.complete and first.prior_tokens == 1 and first.launches_in_scan == 1
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
    # the launch found earlier is a fact and survives the reload (0.3.6 kept it, the first 0.3.7 cut lost it) ...
    assert second.prior_tokens == 1 and second.dead == 1
    # ... but it lies outside the scanned span, so it does not inflate the launch rate
    assert second.launches_in_scan == 0


def test_dropped_creator_transactions_do_not_count_as_scanned():
    dev, sigs, txs, curves = serial_deployer(filler=10, dead=6)
    # the batch loses the creates even on the retry: the covered prefix ends before them
    rpc = CreatorRpc(sigs, txs, curves, drop={f"create{i}" for i in range(6)}, drop_once=False)
    cache = ProfileCache()
    hist, _, _ = _creator_history(rpc, dev, "m1", LAUNCH, 150, cache)
    assert hist.prior_tokens == 0 and not hist.complete and hist.scanned_tx == 10 and hist.ok_tx == 16
    assert hist.source == "rpc(partial)"
    # the transport recovers: the next call scans the rest and the series shows up, no 30-minute blind spot
    rpc.drop.clear()
    later, _, _ = _creator_history(rpc, dev, "m2", LAUNCH + 60, 150, cache)
    assert later.complete and later.prior_tokens == 6 and later.dead == 6
    # a loss that the one retry repairs is covered in the same call
    rpc2 = CreatorRpc(sigs, txs, curves, drop={"create2"}, drop_once=True)
    once, _, _ = _creator_history(rpc2, dev, "m1", LAUNCH, 150, ProfileCache())
    assert once.complete and once.prior_tokens == 6


# --- early wallets: unknown funder, failed exchange check ---------------------------------------------------------
class WalletRpc:
    def __init__(self, first_tx: dict[str, dict], drop: set[str] = frozenset(), busy_error: bool = False):
        self.first_tx = first_tx  # wallet -> its first transaction (fee payer = funder)
        self.drop = set(drop)
        self.busy_error = busy_error

    def get_signatures(self, address, limit=1000, before=None):
        if address in self.first_tx:
            return [{"signature": f"first-{address}", "slot": 1, "blockTime": LAUNCH - 100, "err": None}]
        if self.busy_error:
            raise RpcError("429 after retries")
        return [{"signature": f"x{i}", "slot": i, "blockTime": LAUNCH - 10 * i, "err": None} for i in range(limit)]  # busy funder

    def get_transactions(self, signatures):
        return {s: (None if s.replace("first-", "") in self.drop else self.first_tx.get(s.replace("first-", ""))) for s in signatures}


def _first_tx(wallet: bytes, funder: bytes) -> dict:
    return fake_tx(f"first-{b58encode(wallet)}", 1, LAUNCH - 100, funder, [])


def test_missing_first_transaction_marks_the_funder_unknown_and_skips_the_cache():
    dev, w1, w2 = key(), key(), key()
    rpc = WalletRpc({b58encode(w1): _first_tx(w1, dev), b58encode(w2): _first_tx(w2, dev)}, drop={b58encode(w2)})
    cache = ProfileCache()
    profiles, _, notes = _early_wallets(rpc, [b58encode(w1), b58encode(w2)], LAUNCH, cache, b58encode(dev), None)
    by = {p.address: p for p in profiles}
    assert by[b58encode(w1)].funder == b58encode(dev) and not by[b58encode(w1)].funder_unknown
    assert by[b58encode(w2)].funder is None and by[b58encode(w2)].funder_unknown and any("not loaded" in n for n in notes)
    assert cache.get("wallet", b58encode(w1)) is not None and cache.get("wallet", b58encode(w2)) is None
    balances = {b58encode(w1): 50_000_000_000_000, b58encode(w2): 50_000_000_000_000}
    v = holder_verbund(balances, SUPPLY, by, devs={b58encode(dev)}, creator_funder=None)
    assert v.share == 0.05 and v.unchecked_share == 0.05 and v.checked == 1


def test_failed_exchange_check_leaves_the_source_unknown():
    dev, src, w1, w2 = key(), key(), key(), key()
    txs = {b58encode(w1): _first_tx(w1, src), b58encode(w2): _first_tx(w2, src)}
    ok = WalletRpc(txs)
    profiles, _, _ = _early_wallets(ok, [b58encode(w1), b58encode(w2)], LAUNCH, None, b58encode(dev), None)
    assert all(p.funder == b58encode(src) and p.funder_busy is True for p in profiles)  # 50 signatures: exchange
    bad = WalletRpc(txs, busy_error=True)
    profiles, _, _ = _early_wallets(bad, [b58encode(w1), b58encode(w2)], LAUNCH, None, b58encode(dev), None)
    assert all(p.funder_busy is None for p in profiles)
    balances = {p.address: 30_000_000_000_000 for p in profiles}
    v = holder_verbund(balances, SUPPLY, {p.address: p for p in profiles}, devs={b58encode(dev)}, creator_funder=None)
    assert v.wallets == 0 and v.unchecked_share == 0.06  # shared source, check failed: not clean, not linked


# --- scoring: series rule as documented ---------------------------------------------------------------------------
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
def _wallet_side(engine_box, history, funder_of, deep=None, record=None, hold_creator=False, hold_wallets=False, rounds=None):
    """Fake side tasks: creator history, metadata, deep scan and wallet profiles built from the engine's own state.

    ``rounds`` maps a round name (wallets1, wallets2) to how many of the top holders get a profile; missing rounds
    profile all of them. ``hold_*`` keeps the answer back so the test can deliver it later.
    """
    held: dict[str, list] = {"creator": [], "wallets": []}

    def side(name, fn, done, delay=0.0, group="rpc"):
        if record is not None:
            record.append(name)
        if name == "creator":
            if hold_creator:
                held["creator"].append(done)
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
            n = (rounds or {}).get(name, len(top))
            res = ([WalletProfile(o, 3, funder=funder_of(st, o)) for o, _ in top[:n]], None, [])
            if hold_wallets:
                held["wallets"].append(lambda res=res: done(res))
            else:
                done(res)
        else:
            done(None)

    return side, held


HIST = CreatorHistory(address="c", prior_tokens=2, graduated=1, source="rpc")


def _engine(stufe, side, limit=0.005):
    """The test buyers are small (8 x 0.08 % of the supply): a low limit makes them count."""
    engine, alerts = make_engine(stufe=stufe, tiers=TIERS, side=side)
    engine.rpc = object()
    engine.cfg.fair.max_verbund_share = limit
    return engine, alerts


def test_go_is_gesperrt_when_the_top_holders_hang_on_the_dev():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: st.creator)
    engine, alerts = _engine(2, side)
    box.append(engine)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GESPERRT"]
    assert "Wallet-Verbund" in alerts[1].text and "Dev solscan.io/account/" in alerts[1].text
    fair = alerts[1].state.fair
    assert fair["values"]["verbund_wallets"] == 8 and fair["values"]["verbund_details"][0]["grund"] == "vom Dev finanziert"


def test_go_passes_when_the_top_holders_are_independent():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o)
    engine, alerts = _engine(2, side)
    box.append(engine)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert [a.tier for a in alerts] == ["BLICK", "GO"] and "Verbund 0 %" in alerts[1].text


def test_second_round_profiles_the_unchecked_holders_before_any_verdict():
    # round 1 profiles only 4 of 8 holders (new buyers, failed lookups): the unchecked half decides, so the
    # verdict waits for round 2 instead of recording GESPERRT first and GO later
    names: list[str] = []
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o, record=names, rounds={"wallets1": 4})
    engine, alerts = _engine(2, side, limit=0.002)  # four unchecked holders of 0.08 % each are 0.32 %
    box.append(engine)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    state = engine.tokens[b58encode(mint)]
    assert [a.tier for a in alerts] == ["BLICK"] and state.fair["pending"] == ["Wallets"] and state.wallet_rounds == 1
    engine.tick(T0 + 32)
    assert names.count("wallets1") == 1 and names.count("wallets2") == 1
    assert [a.tier for a in alerts] == ["BLICK", "GO"] and engine.stats.get("gesperrt", 0) == 0
    # the unchecked share stays after the last round: now it is a breach, and nothing follows it
    box2: list = []
    side2, _ = _wallet_side(box2, HIST, lambda st, o: "src-" + o, rounds={"wallets1": 4, "wallets2": 4})
    engine2, alerts2 = _engine(2, side2, limit=0.002)
    box2.append(engine2)
    m2, c2 = key(), key()
    _standard_flow(engine2, m2, c2, _with_meta(m2, c2))
    engine2.tick(T0 + 32)
    engine2.tick(T0 + 38)
    assert [a.tier for a in alerts2] == ["BLICK", "GESPERRT"] and "ungeprüft)" in alerts2[1].text
    assert engine2.tokens[b58encode(m2)].wallet_rounds == 2


def test_budget_exhaustion_waits_instead_of_locking_and_then_lets_go_through():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o)
    engine, alerts = _engine(2, side)
    box.append(engine)
    # the hour's budget runs out right after the creator scan, before the GO candidate's wallet check
    engine.rpc_budget_ok = lambda now=None: not any(st.creator_history for st in engine.tokens.values())
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    state = engine.tokens[b58encode(mint)]
    assert [a.tier for a in alerts] == ["BLICK"] and state.fair["values"]["wallets"] == "budget"
    assert state.fair["pending"] == ["Wallets"] and engine.stats["go_wartet"] == 1 and state.wallet_rounds == 0
    # budget is back: the check runs, GO follows, and no GESPERRT was recorded in between
    engine.rpc_budget_ok = lambda now=None: True
    engine.tick(T0 + 32)
    assert [a.tier for a in alerts] == ["BLICK", "GO"] and engine.stats.get("gesperrt", 0) == 0


def test_a_round_the_spawn_skips_is_not_counted():
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o)
    engine, alerts = _engine(2, side)
    box.append(engine)
    calls = {"n": 0}
    real = engine.rpc_budget_ok

    def flaky(now=None):
        # the first check in _schedule_wallets passes, the second one inside _spawn fails (worker threads spent it)
        calls["n"] += 1
        return calls["n"] % 2 == 1 if any(st.creator_history for st in engine.tokens.values()) else real(now)

    engine.rpc_budget_ok = flaky
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    state = engine.tokens[b58encode(mint)]
    assert state.wallet_rounds == 0 and state.wallet_task is None and state.wallet_skipped
    assert state.fair["values"]["wallets"] == "budget" and "GO" not in [a.tier for a in alerts]
    engine.rpc_budget_ok = lambda now=None: True
    engine.tick(T0 + 32)
    assert [a.tier for a in alerts] == ["BLICK", "GO"]


def test_stufe3_checks_without_waiting_and_still_locks_a_linked_float():
    # answers held back: Stufe 3 does not wait for them
    box: list = []
    side, held = _wallet_side(box, HIST, lambda st, o: st.creator, hold_wallets=True)
    engine, alerts = _engine(3, side)
    box.append(engine)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    assert "GO" in [a.tier for a in alerts] and held["wallets"]
    # the answer arrives at once: the linked float locks GO, documented limit 20 % applies through the stage config
    box2: list = []
    side2, _ = _wallet_side(box2, HIST, lambda st, o: st.creator)
    engine2, alerts2 = _engine(3, side2)
    box2.append(engine2)
    m2, c2 = key(), key()
    _standard_flow(engine2, m2, c2, _with_meta(m2, c2))
    assert "GESPERRT" in [a.tier for a in alerts2] and "GO" not in [a.tier for a in alerts2]
    assert "Wallet-Verbund" in next(a for a in alerts2 if a.tier == "GESPERRT").text


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
    # a slice alone does not lower the score: the candidate reaches GO and gets the scan (no dead zone below GO)
    state = engine2.tokens[b58encode(m2)]
    feats = compute_features(engine2.snapshot(state, T0 + 26), T0 + 26)
    assert feats.creator_sample_capped is False and feats.creator_history_complete is False
    # a 1000-signature page can never be completed: no deep scan is spent on it, the gate judges at once
    capped = CreatorHistory(address="c", prior_tokens=0, source="rpc(partial)", scanned_tx=30, ok_tx=990, sample_capped=True, complete=False)
    names3: list[str] = []
    box3: list = []
    side3, _ = _wallet_side(box3, capped, lambda st, o: "src-" + o, deep=(full, WalletProfile("c", 400), "creatorfirstsig"), record=names3)
    engine3, alerts3 = make_engine(stufe=2, tiers=TIERS, side=side3)
    box3.append(engine3)
    engine3.rpc = object()
    m3, c3 = key(), key()
    _standard_flow(engine3, m3, c3, _with_meta(m3, c3))
    assert "creator_tief" not in names3 and [a.tier for a in alerts3] == ["BLICK", "GESPERRT"]
    assert "Historie unvollständig (30 von 990+ Tx)" in alerts3[1].text


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


def test_early_profiles_wait_for_the_creator_scan_in_every_stage():
    for stufe in (1, 2):
        names: list[str] = []
        box: list = []
        side, held = _wallet_side(box, HIST, lambda st, o: "src-" + o, record=names, hold_creator=True)
        engine, alerts = make_engine(stufe=stufe, tiers=TIERS, side=side)
        box.append(engine)
        engine.rpc = object()
        mint, creator = key(), key()
        engine.on_launch(_with_meta(mint, creator), now=T0)
        feed_buyers(engine, mint, creator, 9, T0 + 3, 1.0, sol=0.12)
        engine.tick(T0 + 14)
        # the creator scan is still out: no early-wallet profiles yet (they would miss the dev's first transaction)
        assert "creator" in names and "profiles" not in names, stufe
        held["creator"][0]((HIST, WalletProfile("c", 400), "creatorfirstsig"))
        engine.tick(T0 + 20)
        assert "profiles" in names, stufe
        assert engine.tokens[b58encode(mint)].creator_first_sig == "creatorfirstsig"


def test_later_rounds_refresh_the_early_wallet_profiles():
    # the early-buyer profile has no exchange status; the wallet round checked the same wallet and knows better
    box: list = []
    side, _ = _wallet_side(box, HIST, lambda st, o: "src-" + o)
    engine, alerts = _engine(2, side)
    box.append(engine)
    mint, creator = key(), key()
    _standard_flow(engine, mint, creator, _with_meta(mint, creator))
    state = engine.tokens[b58encode(mint)]
    stale = WalletProfile(state.trades[1].user, 3, funder="cex")
    state.early_wallets = [stale]
    engine._take_profiles(state, [WalletProfile(stale.address, 3, funder="cex", funder_busy=True)], "cex")
    assert state.early_wallets[0].funder_busy is True and state.creator_funder == "cex"
