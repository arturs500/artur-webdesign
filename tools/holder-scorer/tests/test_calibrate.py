import json
import math

from holder_scorer.calibrate import _num, append_record, evaluate, load_records
from holder_scorer.features import compute_features
from holder_scorer.scoring import score_features
from tests.test_scoring import NOW, organic_snapshot


def test_records_are_append_only_and_outcomes_join(tmp_path):
    path = str(tmp_path / "obs.jsonl")
    v = score_features(compute_features(organic_snapshot(), NOW))
    append_record(path, v)
    append_record(path, v)
    recs = load_records(path)
    assert len(recs) == 2 and recs[0]["outcome"] is None
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"outcome_for": {"mint": recs[1]["mint"], "recorded_at": recs[1]["recorded_at"]}, "outcome": {"grew": True, "holders_later": 90}}) + "\n")
        fh.write("not json\n")
    recs = load_records(path)
    assert recs[0]["outcome"] is None and recs[1]["outcome"]["grew"] is True
    report = evaluate(path)
    assert report.n_total == 2 and report.n_with_outcome == 1 and report.base_rate == 1.0
    assert "Regression erst ab 30" in report.text


def test_evaluate_without_outcomes_and_num_helper(tmp_path):
    path = str(tmp_path / "empty.jsonl")
    assert "Noch keine Ergebnisse" in evaluate(path).text
    assert _num({"features": {"a": float("nan")}}, "a") is None
    assert _num({"features": {"a": True}}, "a") == 1.0
    assert _num({"features": None}, "a") is None
    assert _num({"features": {"a": "3.5"}}, "a") == 3.5
    assert math.isfinite(_num({"features": {"a": 2}}, "a"))
