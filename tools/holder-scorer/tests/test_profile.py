"""Profil (0.3.2): Frühvektor, Bänder und Ähnlichkeit, Aufbau aus dem Tape, Live-Gate (Halter-Anstieg + Profil)."""
from __future__ import annotations

import json

from holder_scorer import profile as pf
from holder_scorer.calibrate import alert_record_extra
from holder_scorer.cli import build_parser, cmd_profil
from holder_scorer.encoding import b58encode
from holder_scorer.live import LiveConfig
from holder_scorer.profile import Tick, build_bands, early_vector, fetch_ticks, profile_from_vectors, similarity
from holder_scorer.pump import TRADE_EVENT_DISC
from tests.helpers import fake_tx, key, trade_event_bytes
from tests.test_live import T0, feed_buyers, launch_msg, make_engine, trade_logs

V_SOL0 = 30_500_000_000
V_TOK0 = 1_073_000_000_000_000 - 20_000_000_000_000
R_TOK0 = 793_100_000_000_000 - 20_000_000_000_000
TOK = 1_000_000_000_000  # 1 Mio Token je Kauf


def tick(ts: float, user: str, buy: bool = True, sol: int = 100_000_000, tok: int = TOK, v_sol: int = V_SOL0, v_tok: int = V_TOK0, slot: int = 0) -> Tick:
    return Tick(ts, user, buy, sol, tok, v_sol, v_tok, max(0, v_sol - 30_000_000_000), max(0, v_tok - 279_900_000_000_000), slot)


def test_early_vector_measures_only_the_past_and_the_holder_rise():
    dev = "D" * 44
    ticks = [tick(1000.0, dev, sol=500_000_000, tok=20_000_000_000_000, slot=100)]
    ticks += [tick(1000.0 + i, f"U{i}", slot=100 + i * 2) for i in range(1, 7)]  # U1 … U6 kaufen bei 1001 … 1006
    ticks.append(tick(1007.0, "U1", buy=False, slot=120))  # U1 verkauft alles
    ticks.append(tick(1040.0, "U7", slot=200))  # Zukunft für at = 1015
    vec = early_vector(ticks, at=1015.0, dev=dev)
    assert vec is not None and vec["age_s"] == 15.0 and vec["n_trades"] == 8
    assert vec["holders"] == 5 and vec["holders_rise"] == 5 and vec["holders_rise_prev"] == 0  # U1 ist wieder raus
    assert vec["buyers"] == 6 and vec["buyers_rise"] == 6 and vec["sells"] == 1 and abs(vec["sell_share"] - 1 / 7) < 1e-3
    assert abs(vec["inflow_sol"] - 0.5) < 1e-9 and abs(vec["max_buy_share"] - 1 / 6) < 1e-3 and vec["median_buy_sol"] == 0.1
    assert abs(vec["dev_share"] - 0.02) < 1e-9 and vec["first_slot_buyers"] == 0  # Slot 100 hat nur den Dev
    assert vec["mc_sol"] > 27 and early_vector(ticks, at=999.0, dev=dev) is None
    # ohne Dev-Angabe gilt der erste Käufer als Dev; das Fenster zählt nur neue Halter
    late = early_vector(ticks, at=1040.0)
    assert late is not None and late["holders"] == 6 and late["holders_rise"] == 1 and late["buyers_rise"] == 1


def _vec(**kw) -> dict:
    base = {"holders": 10, "buyers": 12, "sells": 1, "sell_share": 0.1, "mc_sol": 35.0, "inflow_sol": 1.2, "dev_share": 0.02}
    base.update(kw)
    return base


def test_bands_weights_and_similarity_direction():
    good = [_vec(holders=8 + i, mc_sol=30 + i) for i in range(8)]  # Halter 8–15, MC 30–37
    bad = [_vec(holders=2 + (i % 3), mc_sol=31 + i) for i in range(6)]  # Halter klar darunter, MC überlappt
    bands = build_bands(good, bad, quantile=0.0)
    assert bands["holders"]["lo"] == 8 and bands["holders"]["hi"] == 15 and bands["holders"]["weight"] == 1.0 and bands["holders"]["bad_outside"] == 1.0
    assert bands["mc_sol"]["weight"] < 0.75  # MC trennt kaum: Gewicht nahe 0,5
    assert "holders_rise" not in bands  # Merkmal fehlt in den Vektoren
    prof = profile_from_vectors({f"G{i}": {"30": v} for i, v in enumerate(good)}, {f"B{i}": {"30": v} for i, v in enumerate(bad)}, quantile=0.0)
    assert pf.profile_usable(prof) and pf.profile_checkpoints(prof) == [30.0] and len(prof["hash"]) == 12
    sim_good = similarity(prof, _vec(holders=11, mc_sol=33), 30.0)
    sim_bad = similarity(prof, _vec(holders=3, mc_sol=33), 30.0)
    assert sim_good["aehnlich"] == 1.0 and sim_good["ausserhalb"] == []
    assert sim_bad["aehnlich"] < 0.8 and sim_bad["ausserhalb"] == ["Halter↓"]
    assert similarity(prof, _vec(), 45.0) is None  # kein Checkpoint 45 im Profil
    assert similarity(prof, _vec(holders=99, mc_sol=200), 30.0)["ausserhalb"] == ["Halter↑", "MC↑"]


def _tape_rows(mint: str, t0: int, rise: bool, control: bool = True) -> list[dict]:
    """Ein Coin über 240 s: Dev-Kauf, dann alle 10 s ein neuer Käufer; gute Coins (`rise`) kaufen von Anfang an
    größer (0,1 statt 0,04 SOL) und ziehen ab 60 s an, schlechte flachen ab."""
    dev = "D" + mint[1:]
    rows = [{"mint": mint, "seen_at": t0 + 0.5, "t0": float(t0), "control": control, "backfill": True, "slot": 1000, "ts": t0, "sig": "c", "buy": True, "user": dev, "sol": 500_000_000, "tok": 20_000_000_000_000, "dev": dev, "vS": V_SOL0, "vT": V_TOK0, "rS": 500_000_000, "rT": R_TOK0, "fee": 4_750_000, "creator_fee": 1_500_000}]
    v_sol, v_tok, r_tok = V_SOL0, V_TOK0, R_TOK0
    for i in range(1, 25):
        ts = t0 + i * 10
        if rise:
            sol = 400_000_000 if ts > t0 + 60 else 100_000_000
        else:
            sol = 40_000_000 if ts <= t0 + 60 else 20_000_000
        tok = v_tok * sol // (v_sol + sol)
        v_sol, v_tok, r_tok = v_sol + sol, v_tok - tok, r_tok - tok
        rows.append({"mint": mint, "seen_at": ts + 0.5, "t0": float(t0), "control": control, "backfill": False, "slot": 1000 + i * 40, "ts": ts, "sig": f"s{i}", "buy": True, "user": f"U{i}" + mint[3:], "sol": sol, "tok": tok, "dev": dev, "vS": v_sol, "vT": v_tok, "rS": v_sol - 30_000_000_000, "rT": r_tok, "fee": sol * 95 // 10_000, "creator_fee": sol * 30 // 10_000})
    return rows


def test_build_profile_from_tape_labels_saves_loads_and_checks(tmp_path):
    t = 1_800_000_000
    rows: list[dict] = []
    for i in range(16):
        rows += _tape_rows(("G%02d" % i) + "x" * 41, t + i * 700, rise=True)
    for i in range(12):
        rows += _tape_rows(("B%02d" % i) + "y" * 41, t + 300 + i * 700, rise=False)
    rows += _tape_rows("Z" * 44, t + 50_000, rise=True)[:5]  # endet nach 40 s: zensiert
    tape = tmp_path / "tape.jsonl"
    tape.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    prof, text = pf.build_profile(tape_path=str(tape), split=0.5)
    assert prof["sources"]["tape_coins"] == 29 and prof["sources"]["tape_zensiert"] == 1
    assert len(prof["good"]) == 16 and len(prof["bad"]) == 12 and pf.profile_checkpoints(prof) == [10.0, 20.0, 30.0, 45.0]
    cp45 = prof["checkpoints"]["45"]
    assert cp45["n_good"] == 16 and cp45["n_bad"] == 12
    # Halter kommen bei guten wie schlechten Coins im gleichen Takt (Gewicht 0,5); die Kaufgröße trennt (Gewicht 1,0)
    assert abs(cp45["bands"]["holders"]["weight"] - 0.5) < 1e-9 and cp45["bands"]["median_buy_sol"]["weight"] == 1.0
    check = prof["pruefung"]
    assert "Prüfung (Zeitsplit)" in text and check["n_train"] == 14 and check["n_test"] == 14 and check["checkpoint"] == 45.0
    assert check["bestanden"]["n"] == 9 and check["bestanden"]["treffer"] == 9 and check["nicht_bestanden"]["n"] == 5 and check["nicht_bestanden"]["treffer"] == 0
    assert check["bootstrap"]["lo"] > 0 and "trennt" in text and "gut = graduiert oder Netto-Rendite > 0" in prof["label_rule"]
    out = tmp_path / "profil.json"
    pf.save_profile(prof, str(out))
    loaded = pf.load_profile(str(out))
    assert loaded["hash"] == prof["hash"] and "Checkpoint 45 s" in pf.describe_profile(loaded)
    # CLI: bauen schreibt, zeigen liest; ohne Quelle Fehler
    args = build_parser().parse_args(["profil", "bauen", "--tape", str(tape), "--out", str(tmp_path / "p2.json"), "--split", "0"])
    assert args.func is cmd_profil and cmd_profil(args) == 0 and (tmp_path / "p2.json").exists()
    assert cmd_profil(build_parser().parse_args(["profil", "zeigen", str(out)])) == 0
    assert cmd_profil(build_parser().parse_args(["profil", "bauen", "--out", str(tmp_path / "x.json")])) == 2
    # zu wenige gute Coins: kein Profil
    small = tmp_path / "small.jsonl"
    small.write_text("\n".join(json.dumps(r) for r in rows[: 25 * 3]) + "\n", encoding="utf-8")
    prof_small, text_small = pf.build_profile(tape_path=str(small), split=0.0)
    assert not pf.profile_usable(prof_small) and "Kein Profil" in text_small
    assert cmd_profil(build_parser().parse_args(["profil", "bauen", "--tape", str(small), "--out", str(tmp_path / "none.json")])) == 1


def test_label_from_rows_reads_rise_graduation_and_censoring():
    from holder_scorer.replay import Costs

    good = pf.label_from_rows(_tape_rows("G" * 44, 1_800_000_000, rise=True), 60.0, 180.0, 0.08, Costs())
    bad = pf.label_from_rows(_tape_rows("B" * 44, 1_800_000_000, rise=False), 60.0, 180.0, 0.08, Costs())
    assert good["gut"] and good["r_cons"] > 0 and not good["graduiert"]
    assert not bad["gut"] and bad["r_cons"] < 0
    short = pf.label_from_rows(_tape_rows("Z" * 44, 1_800_000_000, rise=True)[:5], 60.0, 180.0, 0.08, Costs())
    assert short["zensiert"] and short["handelbar"] is None
    grad = _tape_rows("Q" * 44, 1_800_000_000, rise=True)[:12]
    grad[-1]["rT"] = 0  # Kurve voll: Graduation vor dem Ausstieg zählt als gut, nicht als zensiert
    lab = pf.label_from_rows(grad, 60.0, 180.0, 0.08, Costs())
    assert lab["gut"] and lab["graduiert"]


def test_live_gate_needs_holder_rise_and_profile_similarity(tmp_path):
    # 1. Halter-Anstieg: ohne neue Halter in den letzten 15 s kein GO, einmal gezählt
    def run(engine, mint, creator):
        """Gleicher Ablauf wie test_blick_then_go_then_rug: BLICK bei 12 s, die Score-Bedingungen für GO stehen bei 26 s."""
        engine.on_launch(launch_msg(mint, creator), now=T0)
        # first buyer inside the creation window: defines slot 0, so the bundle window is observed, not guessed
        engine.on_logs(b58encode(mint), 5000, "early", None, trade_logs(mint, key(), 0.05, 500_000.0, True, int(T0), creator), now=T0 + 0.4)
        feed_buyers(engine, mint, creator, 6, T0 + 3, 1.5, sol=0.12)
        engine.tick(T0 + 12)
        feed_buyers(engine, mint, creator, 10, T0 + 14, 1.0)
        engine.tick(T0 + 26)
        return engine.tokens[b58encode(mint)]

    engine, alerts = make_engine(stufe=2)
    engine.cfg.go_min_holder_rise = 50
    mint, creator = key(), key()
    state = run(engine, mint, creator)
    assert [a.tier for a in alerts] == ["BLICK"] and "Halter +" in alerts[0].text.splitlines()[0]
    assert engine.stats["go_profil"] == 1 and state.profil_blockiert and state.profil["anstieg"] >= 2
    assert set(state.profil["vektoren"]) == {"10", "20"} and state.profil["aehnlich"] is None  # Vektoren auch ohne Profil
    engine.cfg.go_min_holder_rise = 2
    engine.tick(T0 + 31)
    assert [a.tier for a in alerts] == ["BLICK", "GO"] and "Halter +" in alerts[1].text.splitlines()[0]
    rec = alert_record_extra(alerts[1], 2, "abc", "0.3.2", engine.cfg, engine.scoring)
    assert rec["profil"]["anstieg"] >= 2 and "20" in rec["profil"]["vektoren"] and "30" in rec["profil"]["vektoren"]
    # 2. Profil: ein Coin, der nicht wie die guten aussieht, bekommt kein GO; passt er, steht die Ähnlichkeit im Kopf
    strict = {"version": 1, "checkpoints": {"20": {"n_good": 10, "n_bad": 0, "bands": {"mc_sol": {"lo": 100.0, "hi": 200.0, "med": 150.0, "n": 10, "weight": 1.0}, "buyers": {"lo": 5, "hi": 40, "med": 12, "n": 10, "weight": 1.0}}}}}
    strict["hash"] = pf.profile_hash(strict)
    engine2, alerts2 = make_engine(stufe=2)
    engine2.profile = strict
    mint2, creator2 = key(), key()
    state2 = run(engine2, mint2, creator2)
    assert [a.tier for a in alerts2] == ["BLICK"] and "Profil ?" in alerts2[0].text.splitlines()[0]  # mit 12 s noch vor dem 20-s-Checkpoint
    assert engine2.stats["go_profil"] == 1 and state2.profil["checkpoint"] == 20.0 and state2.profil["hash"] == strict["hash"]
    assert state2.profil["aehnlich"] == 0.5 and state2.profil["ausserhalb"] == ["MC↓"]
    strict["checkpoints"]["20"]["bands"]["mc_sol"].update(lo=28.0, hi=60.0)
    engine2.tick(T0 + 31)
    assert [a.tier for a in alerts2] == ["BLICK", "GO"] and "Profil 100 %" in alerts2[1].text.splitlines()[0] and "nach BLICK" in alerts2[1].text
    # 3. Pflicht ohne Profil: kein GO
    cfg, _ = LiveConfig.for_stufe(2)
    assert cfg.go_min_holder_rise == 2 and LiveConfig.for_stufe(1)[0].go_min_holder_rise == 3
    engine3, alerts3 = make_engine(stufe=2)
    engine3.cfg.profile_required = True
    mint3, creator3 = key(), key()
    run(engine3, mint3, creator3)
    assert [a.tier for a in alerts3] == ["BLICK"] and engine3.stats["go_profil"] == 1
    # 4. Tape-Zeilen tragen den Dev, CLI-Argumente landen in der Konfiguration
    engine4, _ = make_engine(stufe=1)
    engine4.cfg.tape_path = str(tmp_path / "tape.jsonl")
    engine4.cfg.tape_sample = 1.0
    mint4, creator4 = key(), key()
    engine4.on_launch(launch_msg(mint4, creator4), now=T0)
    feed_buyers(engine4, mint4, creator4, 2, T0 + 3, 1.0)
    row = json.loads((tmp_path / "tape.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["dev"] == b58encode(creator4)
    args = build_parser().parse_args(["live", "--profil", "p.json", "--profil-min", "0.8", "--profil-pflicht", "--holder-anstieg", "4"])
    assert args.profil == "p.json" and args.profil_min == 0.8 and args.profil_pflicht and args.holder_anstieg == 4


class HistoryRpc:
    def __init__(self, mint58: str, sigs: list[dict], txs: dict):
        self.mint, self.sigs, self.txs = mint58, sigs, txs
        self.stats = {"requests": 0, "posts": 0, "retries": 0, "by_method": {}}

    def get_signatures(self, address, limit=1000, before=None):
        assert address == self.mint
        self.stats["requests"] += 1
        return list(self.sigs) if before is None else []

    def get_transactions(self, signatures):
        self.stats["requests"] += len(signatures)
        return {s: self.txs.get(s) for s in signatures}


def test_fetch_ticks_from_chain_history_and_mints_file(tmp_path):
    mint, creator = key(), key()
    m58 = b58encode(mint)
    t0 = 1_800_000_000
    vsol, vtok = 30_500_000_000, V_TOK0
    sigs, txs = [], {}
    for i, dt in enumerate([0, 5, 12, 30, 400]):
        lam, raw = 100_000_000, 3_000_000_000_000
        vsol, vtok = vsol + lam, vtok - raw
        payer = key()
        ev = TRADE_EVENT_DISC + trade_event_bytes(mint, payer, lam, raw, True, t0 + dt, creator, reserves=(vsol, vtok))
        sigs.append({"signature": f"s{i}", "slot": 100 + i, "blockTime": t0 + dt, "err": None})
        txs[f"s{i}"] = fake_tx(f"s{i}", 100 + i, t0 + dt, payer, [ev])
    sigs.reverse()
    rpc = HistoryRpc(m58, sigs, txs)
    ticks, info = fetch_ticks(rpc, m58, seconds=60.0)
    assert info["pages"] == 1 and info["signatures"] == 5 and info["transactions"] == 4 and not info["abgebrochen"]
    assert [t.ts - t0 for t in ticks] == [0, 5, 12, 30] and ticks[0].slot == 100 and ticks[-1].r_tok > 0
    vecs = pf.vectors_at_checkpoints(ticks, None, (10.0, 20.0))
    assert vecs["10"]["buyers"] == 1 and vecs["20"]["buyers"] == 2  # der erste Käufer gilt ohne Dev-Angabe als Dev
    # mehr Seiten als erlaubt: Anfang nicht erreicht, keine Ticks
    big = HistoryRpc(m58, [dict(s) for s in sigs] * 200, txs)
    assert fetch_ticks(big, m58, seconds=60.0, max_pages=1) == ([], {"pages": 1, "signatures": 1000, "transactions": 0, "abgebrochen": True})
    f = tmp_path / "mints.txt"
    f.write_text(f"# Beispiele\n{m58} gut\n{'A' * 44} schlecht\n{'B' * 44}\n", encoding="utf-8")
    assert pf.parse_mints_file(str(f)) == [(m58, True), ("A" * 44, False), ("B" * 44, None)]
    args = build_parser().parse_args(["profil", "bauen", "--mints", str(f), "--out", str(tmp_path / "p.json"), "--dry-run"])
    assert cmd_profil(args) == 0 and not (tmp_path / "p.json").exists()
