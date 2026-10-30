"""
The agent loop: call the model, run any tools it asks for, repeat until it answers.
Then run the variant's validator, if it has one.

  python -m agent.run --variant v3 --question Q16 [--mode mock|live]

Built by Avinash Rayudu.
"""
from __future__ import annotations

import argparse
import importlib
import json
import time

from variants.common import parse_final

VARIANTS = {"v1": "variants.v1_single_prompt.variant", "v2": "variants.v2_sql_tools.variant",
            "v3": "variants.v3_skills_validators.variant"}
TOOL_RESULT_CAP = 20000
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def load_variant(key):
    return importlib.import_module(VARIANTS[key])


def run_agent(model, spec, context):
    messages = [{"role": "user", "content": spec["user"]}]
    tool_texts, calls, events = [], [], []
    usage = {"input_tokens": 0, "output_tokens": 0}
    t0 = time.time()
    final, revisions, forced, fault = "", 0, False, None
    budget = spec["max_turns"] + (2 if spec["validator"] else 0)
    for turn in range(budget):
        resp = model.create(spec["system"], messages, spec["tools"], context)
        u = resp.get("usage", {})
        for k in USAGE_KEYS:
            if k in usage or u.get(k):
                usage[k] = usage.get(k, 0) + int(u.get(k) or 0)
        if resp.get("_cost_usd") is not None:
            usage["cost_usd"] = round(usage.get("cost_usd", 0) + resp["_cost_usd"], 8)
        fault = resp.get("_mock_fault", fault)
        messages.append({"role": "assistant", "content": resp["content"]})
        uses = [b for b in resp["content"] if b.get("type") == "tool_use"]
        if uses and resp.get("stop_reason") == "tool_use":
            out = []
            for u in uses:
                impl = spec["tool_impl"].get(u["name"])
                res = impl(u["input"]) if impl else json.dumps({"error": f"unknown tool {u['name']}"})
                res = res[:TOOL_RESULT_CAP]
                tool_texts.append(res)
                calls.append({"tool": u["name"], "input": u["input"]})
                out.append({"type": "tool_result", "tool_use_id": u["id"], "content": res})
            messages.append({"role": "user", "content": out})
            continue
        final = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
        if spec["validator"]:
            err = spec["validator"](final, tool_texts)
            if err and revisions == 0:
                revisions += 1
                events.append(err)
                messages.append({"role": "user", "content": "Validator: " + err})
                continue
            if err:
                events.append(err)
                forced = True
                final = json.dumps({"answer": None, "abstain": True, "reason": "validator rejected the answer twice"})
        break
    else:
        events.append("turn budget exhausted")
    return {"final_text": final, "parsed": parse_final(final), "usage": usage, "latency_s": round(time.time() - t0, 3),
            "turns": len([m for m in messages if m["role"] == "assistant"]), "tool_calls": calls,
            "validator_events": events, "forced_abstain": forced, "mock_fault": fault}


def main():
    from agent.mock import MockModel
    from agent.models import AnthropicModel
    from evals.harness import question_text
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v3", choices=list(VARIANTS))
    ap.add_argument("--question", default="Q16")
    ap.add_argument("--mode", default="mock", choices=["mock", "faulty", "live"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    model = AnthropicModel(a.model) if a.mode == "live" else MockModel("faulty" if a.mode == "faulty" else "oracle")
    v = load_variant(a.variant)
    r = run_agent(model, v.build(question_text(a.question)), {"qid": a.question, "variant": v.NAME, "run": 0})
    print(json.dumps({k: r[k] for k in ("parsed", "usage", "turns", "tool_calls", "validator_events")}, indent=1,
                     default=str))


if __name__ == "__main__":
    main()
