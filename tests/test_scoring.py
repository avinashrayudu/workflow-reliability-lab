"""The scorer: formats it accepts, mistakes it must catch."""
from evals.score import score_brief, score_question
from evals.validate_scorer import validate


def test_money_formats_and_tolerance():
    assert score_question("Q01", {"answer": "$194,498.04", "abstain": False})["correct"]
    assert score_question("Q01", {"answer": 194498, "abstain": False})["correct"]
    r = score_question("Q01", {"answer": 194498.04 * 1.01, "abstain": False})
    assert r["outcome"] == "wrong_number" and abs(r["numeric_error"] - 0.01) < 1e-6
    assert score_question("Q06", {"answer": 7578.30, "abstain": False})["outcome"] == "wrong_number"   # sign


def test_dates_entities_sets():
    assert score_question("Q02", {"answer": "Nov 16, 2026", "abstain": False})["correct"]
    assert score_question("Q20", {"answer": "Fernwood Goods", "abstain": False})["correct"]
    assert score_question("Q21", {"answer": ["tidewater-swim", "bramble-pet", "north-arc-outdoor", "hollis-home"],
                                  "abstain": False})["correct"]
    assert score_question("Q21", {"answer": ["tidewater-swim"], "abstain": False})["outcome"] == "wrong_set"


def test_abstention_both_ways():
    assert score_question("Q28", {"answer": None, "abstain": True})["correct"]
    assert score_question("Q28", {"answer": 51234.5, "abstain": False})["outcome"] == "missed_abstention"
    assert score_question("Q33", {"answer": None, "abstain": True})["outcome"] == "false_abstention"
    assert score_question("Q01", None)["outcome"] == "format_error"


def test_brief_flags_invented_dollar_figures():
    good = {"low_point": 186240.72, "low_point_week": "2026-11-16", "gap_to_buffer": 113759.28, "draw": 125000,
            "interest_one_week": 264.42, "top_refund_sku": "FW-2201", "payout_variance": -7578.3,
            "largest_bill_this_week": "PO-BFCM-BAL",
            "narrative": "Cash bottoms at $186,241 the week of Nov 16. Draw $125K; the $520,000 PO is due."}
    r = score_brief(good)
    assert r["correct"] and r["dollar_figures"] == 3 and r["unsupported"] == 0
    bad = dict(good, narrative=good["narrative"] + " Expect $77,777 more from wholesale.")
    assert score_brief(bad)["unsupported"] == 1


def test_scorer_catches_every_injected_mistake():
    res = validate(n=2, write=False)
    assert res["all_faults_caught"] and res["no_false_flags"]
    assert len(res["by_fault"]) >= 8
