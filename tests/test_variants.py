"""The variants' tools and validators, and the live adapter's request shape (no network)."""
import json

import pytest

from agent.run import run_agent
from variants.v2_sql_tools.variant import run_sql
from variants.v3_skills_validators import tools
from variants.v3_skills_validators.variant import build, load_skill, validate


def test_sql_tool_is_read_only():
    assert "error" in json.loads(run_sql("delete from brands"))
    assert "error" in json.loads(run_sql("select 1; drop table brands"))
    r = json.loads(run_sql("with x as (select 1) insert into brands (brand_id) select * from x"))
    assert "error" in r and "readonly" in r["error"].replace(" ", "").lower()
    assert json.loads(run_sql("select count(*) from brands"))["rows"] == [[10]]


def test_tools_flag_the_planted_gaps():
    assert json.loads(tools.call("variance", {"brand_id": "copperleaf-tea", "line": "all"}))["missing_data"]
    assert json.loads(tools.call("bills", {"brand_id": "saltmarsh-apparel"}))["missing_data"]
    assert json.loads(tools.call("driver_variance", {"brand_id": "lark-and-pine", "kind": "refunds_by_sku"}))[
        "missing_data"]
    assert not json.loads(tools.call("cash_path", {"brand_id": "saltmarsh-apparel", "basis": "forecast"}))[
        "missing_data"]


def test_validator_provenance_and_coverage():
    res = [tools.call("cash_path", {"brand_id": "fernwood-goods", "basis": "forecast"})]
    assert validate('{"answer": 194498.04, "abstain": false, "reason": "x"}', res) is None
    assert "do not appear" in validate('{"answer": 190000, "abstain": false, "reason": "x"}', res)
    gap = [tools.call("variance", {"brand_id": "copperleaf-tea", "line": "all"})]
    assert "abstain" in validate('{"answer": 1.0, "abstain": false, "reason": "x"}', gap)
    assert validate('{"answer": null, "abstain": true, "reason": "x"}', gap) is None
    # skill text mentions "missing_data": true; it must not count as a tool flag
    assert validate('{"answer": 194498.04, "abstain": false, "reason": "x"}', [load_skill("cash-position")] + res) is None


class Scripted:
    """Stands in for the API: returns canned Messages-API responses in order."""
    live = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, system, messages, tools, context=None):
        self.requests.append(json.loads(json.dumps(messages)))
        return self.responses.pop(0)


def test_agent_loop_runs_tools_and_sends_back_a_rejected_answer():
    u = {"input_tokens": 10, "output_tokens": 5}
    m = Scripted([
        {"content": [{"type": "tool_use", "id": "t1", "name": "cash_path",
                      "input": {"brand_id": "fernwood-goods", "basis": "forecast"}}], "stop_reason": "tool_use",
         "usage": u},
        {"content": [{"type": "text", "text": '{"answer": 190000, "abstain": false, "reason": "rounded"}'}],
         "stop_reason": "end_turn", "usage": u},
        {"content": [{"type": "text", "text": '{"answer": 194498.04, "abstain": false, "reason": "tool"}'}],
         "stop_reason": "end_turn", "usage": u},
    ])
    r = run_agent(m, build("low point?"), {"qid": "Q01", "variant": "v3", "run": 0})
    assert r["parsed"]["answer"] == 194498.04 and len(r["validator_events"]) == 1
    assert r["usage"] == {"input_tokens": 30, "output_tokens": 15}
    tool_result = m.requests[1][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "t1"


def test_live_adapter_builds_a_messages_request(monkeypatch):
    import agent.models as M
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn",
                               "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()

    def fake_urlopen(req, timeout=None):
        seen["url"], seen["headers"], seen["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
        return Resp()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(M.urllib.request, "urlopen", fake_urlopen)
    M.AnthropicModel().create("sys", [{"role": "user", "content": "hi"}], [{"name": "t", "description": "d",
                                                                           "input_schema": {"type": "object"}}])
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    h = {k.lower(): v for k, v in seen["headers"].items()}
    assert h["x-api-key"] == "test-key" and h["anthropic-version"] == "2023-06-01"
    body = seen["body"]
    assert body["system"] == [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    assert body["tools"][0]["name"] == "t" and body["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    # the end of the conversation is marked for caching, so the next turn reads it from cache
    assert body["messages"][-1]["content"][-1] == {"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}


def test_caching_marks_the_copy_not_the_conversation():
    from agent.models import cached_messages
    convo = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]}]
    sent = cached_messages(convo)
    assert "cache_control" in sent[-1]["content"][-1] and "cache_control" not in convo[-1]["content"][-1]


def test_cached_tokens_are_priced_at_cache_rates():
    from agent.models import price, price_usage
    # Sonnet 5.5: $2 input, $10 output, $2.50 cache write, $0.10 cache read per million tokens
    assert abs(price("claude-sonnet-5-5", 1_000_000, 0, 0, 0) - 2.0) < 1e-9
    assert abs(price("claude-sonnet-5-5", 0, 0, 1_000_000, 0) - 2.5) < 1e-9
    assert abs(price("claude-sonnet-5-5", 0, 0, 0, 1_000_000) - 0.10) < 1e-9
    # Haiku 5.5's tier counts cached tokens toward the 100K prompt length
    lo = price_usage("claude-haiku-5-5", {"input_tokens": 1000, "cache_read_input_tokens": 50_000})
    hi = price_usage("claude-haiku-5-5", {"input_tokens": 1000, "cache_read_input_tokens": 150_000})
    assert abs(lo - (1000 * 0.10 + 50_000 * 0.01) / 1e6) < 1e-12
    assert abs(hi - (1000 * 0.50 + 150_000 * 0.05) / 1e6) < 1e-12


def test_live_mode_without_a_key_stops_cleanly(monkeypatch):
    import agent.models as M
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        M.AnthropicModel()
