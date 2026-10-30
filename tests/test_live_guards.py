"""The live-run guards: spend cap, no overwrite, provenance, and the preflight (no network, no key)."""
import json

import pytest

from evals import harness, preflight


class Expensive:
    """A scripted 'model' that answers at once, at a known token cost per call."""
    live = True
    model = "claude-sonnet-5-5"

    def create(self, system, messages, tools, context=None):
        return {"content": [{"type": "text", "text": '{"answer": null, "abstain": true, "reason": "x"}'}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}


def test_spend_cap_stops_the_run_and_marks_it_incomplete(tmp_path):
    stop = {}
    # each call is priced at $2.00 (1M input tokens at Sonnet 5.5), so a $5 cap allows 3 calls
    recs = harness.run("live", ["v2"], 2, ["Q01", "Q02", "Q03"], "claude-sonnet-5-5", progress=False,
                       max_usd=5.0, model=Expensive(), stop=stop)
    assert len(recs) == 3 and stop["budget_reached"] and stop["spent_usd"] == 6.0
    s = harness.write("live", recs, "claude-sonnet-5-5", 2, complete=False, spent_usd=6.0, root=tmp_path)
    assert s["complete"] is False and "INCOMPLETE" in (tmp_path / "live" / "summary.md").read_text()


def test_a_live_result_is_never_overwritten(tmp_path):
    recs = harness.run("live", ["v2"], 1, ["Q01"], "claude-sonnet-5-5", progress=False, model=Expensive())
    harness.write("live", recs, "claude-sonnet-5-5", 1, root=tmp_path)
    with pytest.raises(SystemExit):
        harness.write("live", recs, "claude-sonnet-5-5", 1, root=tmp_path)
    harness.write("live", recs, "claude-sonnet-5-5", 1, root=tmp_path, overwrite=True)


def test_summary_records_provenance(tmp_path):
    recs = harness.run("mock", ["v2"], 1, ["Q01"], progress=False)
    s = harness.write("mock", recs, "mock-oracle", 1, price_model="claude-sonnet-5-5", root=tmp_path)
    p = s["provenance"]
    assert len(p["data_sha"]) == 16 and len(p["questions_sha"]) == 16 and len(p["answer_key_sha"]) == 16


def test_preflight_is_pending_without_a_key_and_never_prints_it():
    res = dict((n, ok) for n, ok, _ in preflight.checks("claude-sonnet-5-5", env={}))
    assert res["ANTHROPIC_API_KEY is set"] is False
    assert res["answer key matches the data and questions"] is True
    with_key = preflight.checks("claude-sonnet-5-5", env={"ANTHROPIC_API_KEY": "sk-secret"})
    assert all("sk-secret" not in note for _, _, note in with_key)


def test_parallel_runs_respect_the_cap_and_keep_order(tmp_path):
    stop = {}
    recs = harness.run("live", ["v2"], 2, ["Q01", "Q02", "Q03"], "claude-sonnet-5-5", progress=False,
                       max_usd=5.0, model=Expensive(), stop=stop, workers=3)
    # with 3 calls in flight the cap can be passed by at most the calls already running
    assert stop["budget_reached"] and 3 <= len(recs) <= 5
    keys = [(r["qid"], r["run"]) for r in recs]
    assert keys == sorted(keys)


def test_finished_runs_are_saved_as_they_land_and_a_resume_skips_them(tmp_path):
    saved = []
    first = harness.run("live", ["v2"], 1, ["Q01", "Q02"], "claude-sonnet-5-5", progress=False, model=Expensive(),
                        sink=saved.append)
    assert len(saved) == 2
    calls = []

    class Counting(Expensive):
        def create(self, *a, **k):
            calls.append(1)
            return super().create(*a, **k)

    again = harness.run("live", ["v2"], 1, ["Q01", "Q02", "Q03"], "claude-sonnet-5-5", progress=False,
                        model=Counting(), prior=first)
    assert len(again) == 3 and len(calls) == 1


def test_wrong_answers_get_a_plain_language_error_type():
    et = harness.error_type
    assert et({"qid": "Q01", "outcome": "correct"}) is None
    assert et({"qid": "Q01", "outcome": "wrong_number", "numeric_error": 0.004}) == "number off by under 1%"
    assert et({"qid": "Q01", "outcome": "wrong_number", "numeric_error": 0.2}) == "number off by 1% or more"
    assert et({"qid": "Q30", "outcome": "missed_abstention"}) == "answered when the data was missing"
    assert et({"qid": "Q01", "outcome": "false_abstention", "forced_abstain": True}) == "validator forced a refusal"
    assert et({"qid": "B01", "outcome": "wrong_brief", "unsupported": 2}) == "brief: dollar figure not in the data"
