"""Two independent computations of every answer must agree, through every variant's interface."""
import json
from pathlib import Path

from evals.harness import ALL_IDS, run, summarize

ROOT = Path(__file__).resolve().parent.parent


def test_eval_set_has_at_least_25_graded_questions_and_abstentions():
    truth = json.loads((ROOT / "truth" / "answers.json").read_text())["answers"]
    qs = [k for k in truth if k.startswith("Q")]
    assert len(qs) >= 25
    assert sum(truth[k] == "ABSTAIN" for k in qs) >= 3


def test_reference_solutions_match_truth_through_every_variant():
    recs = run("mock", ["v1", "v2", "v3"], 1, ALL_IDS, progress=False)
    bad = [(r["variant"], r["qid"], r["outcome"]) for r in recs if not r["correct"]]
    assert bad == []


def test_mock_is_deterministic():
    a = run("mock", ["v2"], 2, ["Q01", "Q16", "Q28"], progress=False)
    assert summarize(a, "claude-sonnet-5-5")["v2"]["consistency_all_runs_agree"] == 1.0


def test_truth_reproduces_forecast_health_monitor():
    truth = json.loads((ROOT / "truth" / "answers.json").read_text())["answers"]
    assert round(truth["Q01"]) == 194498 and truth["Q02"] == "2026-11-16" and truth["Q04"] == 125000
