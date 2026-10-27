"""
The offline mock model. It is deterministic and it is not a language model.

It exists so the whole pipeline runs without an API key: prompts, tools, the agent loop,
validators, scoring, the report and the cost estimate. Its scores measure the plumbing,
not a model. The README and every report it produces say so.

  oracle   Replays the reference solution in evals/mock_plans.yaml through the variant's own
           interface.
             v1: it rebuilds the tables from the CSV text inside the prompt and runs the
                 reference SQL. This proves the prompt really holds what each question needs.
             v2: it calls run_sql with the reference query.
             v3: it loads the skill and calls the domain tools.
           A perfect score here means every question can be answered through that variant.

  faulty   The oracle plus injected mistakes of known types (wrong sign, wrong scale, 3% drift,
           wrong week, wrong entity, missed or false abstention, broken format, an invented
           dollar figure in the brief). It runs at a set rate, chosen by a hash of
           (question, variant, run). The scorer must catch every injected mistake;
           evals/validate_scorer.py checks that it does.

Usage and cost are estimates at about 4 characters per token of the real prompts, so the
dry-run cost of a live run is grounded in the actual prompt sizes.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import yaml

from agent.models import estimate_tokens
from variants.common import connect_ro

ROOT = Path(__file__).resolve().parent.parent
PLANS = yaml.safe_load((ROOT / "evals" / "mock_plans.yaml").read_text())
QTYPE = {q["id"]: q["type"] for q in yaml.safe_load((ROOT / "truth" / "questions.yaml").read_text())["questions"]}
FAULTS = {
    "money": ["sign_flip", "scale_1000", "drift_3pct", "neighbor_value"],
    "date": ["shift_week"],
    "text": ["wrong_entity"],
    "int": ["off_by_one"],
    "set": ["drop_item"],
    "abstain": ["missed_abstention"],
}


def _h(*parts) -> float:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


# ------------------------------------------------------------------------------------------- evaluation
def _sql(con, plan_sql, shape="scalar"):
    rows = con.execute(plan_sql).fetchall()
    if shape == "list":
        return [r[0] for r in rows]
    if not rows or rows[0][0] is None:
        return None
    return rows[0][0]


def _pick(obj, path):
    for part in str(path).split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            if "=" in part:
                k, v = part.split("=", 1)
                obj = next((x for x in obj if str(x.get(k)) == v), None)
            else:
                i = int(part)
                obj = obj[i] if i < len(obj) else None
        else:
            obj = obj.get(part)
    return obj


def _db_from_prompt(system: str):
    con = sqlite3.connect(":memory:")
    for name, body in re.findall(r"### table: (\w+)\n```csv\n(.*?)\n```", system, re.S):
        rd = csv.reader(io.StringIO(body))
        cols = next(rd)
        con.execute(f"create table {name} ({', '.join(cols)})")
        rows = [[None if v == "" else _num(v) for v in r] for r in rd]
        con.executemany(f"insert into {name} values ({', '.join('?' * len(cols))})", rows)
    return con


def _num(v):
    for f in (int, float):
        try:
            return f(v)
        except ValueError:
            pass
    return v


def _final(obj):
    return f"Working done with the data provided.\n{json.dumps(obj)}"


def _answer_obj(value, reason="computed from the data"):
    if value is None:
        return {"answer": None, "abstain": True, "reason": "the data needed is missing"}
    if isinstance(value, float):
        value = round(value, 2)
    return {"answer": value, "abstain": False, "reason": reason}


def _brief_obj(fields: dict):
    f = fields
    if any(v is None for v in f.values()):
        f = {k: v for k, v in f.items()}
    narr = (f"Cash bottoms at ${f['low_point']:,.2f} in the week of {f['low_point_week']}, "
            f"${f['gap_to_buffer']:,.2f} under the buffer. Draw ${f['draw']:,.0f} on the credit line; one week costs "
            f"about ${f['interest_one_week']:,.2f} in interest. Shopify payouts are ${abs(f['payout_variance']):,.2f} "
            f"{'under' if f['payout_variance'] < 0 else 'over'} forecast so far, led by refunds on {f['top_refund_sku']}. "
            f"The largest bill this week is {f['largest_bill_this_week']}.")
    return dict(f, narrative=narr)


# ------------------------------------------------------------------------------------------- faults
def _inject(obj, qid, variant, run, rate, attempt, tool_numbers):
    """Returns (possibly altered obj, fault name or None)."""
    if _h("fault?", qid, variant, run, attempt) >= rate:
        return obj, None
    if _h("format?", qid, variant, run, attempt) < 0.08:
        return "BROKEN", "format_error"
    if qid == "B01":
        bad = dict(obj)
        bad["narrative"] = obj["narrative"] + " Holiday sales should add about $123,457 next week."
        return bad, "unsupported_number"
    qt = QTYPE[qid]
    if qt != "abstain" and _h("abst?", qid, variant, run, attempt) < 0.12:
        return {"answer": None, "abstain": True, "reason": "unsure"}, "false_abstention"
    kinds = FAULTS[qt]
    kind = kinds[int(_h("kind", qid, variant, run, attempt) * len(kinds)) % len(kinds)]
    a = dict(obj)
    v = obj.get("answer")
    if kind == "sign_flip":
        a["answer"] = -v if v else 1.0
    elif kind == "scale_1000":
        a["answer"] = round(v / 1000, 2) if v else 1.0
    elif kind == "drift_3pct":
        a["answer"] = round(v * 1.03, 2) if v else 1.0
    elif kind == "neighbor_value":
        others = [n for n in tool_numbers if v and abs(abs(n) - abs(v)) > max(1.0, 0.001 * abs(v)) and abs(n) > 100]
        a["answer"] = others[int(_h("nb", qid, run) * len(others))] if others else round((v or 0) + 1000, 2)
    elif kind == "shift_week":
        a["answer"] = (date.fromisoformat(v) + timedelta(days=7)).isoformat()
    elif kind == "wrong_entity":
        a["answer"] = "fernwood-goods" if v != "fernwood-goods" else "hollis-home"
        if str(v).startswith(("FW-", "PO-", "TPL-")):
            a["answer"] = {"FW-2201": "FW-2205"}.get(v, "FRT-BFCM")
    elif kind == "off_by_one":
        a["answer"] = v + 1
    elif kind == "drop_item":
        a["answer"] = v[1:]
    elif kind == "missed_abstention":
        a = {"answer": 0, "abstain": False, "reason": "assumed zero"}
    return a, kind


# ------------------------------------------------------------------------------------------- the model
class MockModel:
    live = False

    def __init__(self, kind="oracle", fault_rate=0.25):
        self.kind = kind
        self.fault_rate = fault_rate if kind == "faulty" else 0.0
        self.model = f"mock-{kind}"

    def _respond(self, content, system, messages, tools, stop):
        usage = {"input_tokens": estimate_tokens(system) + estimate_tokens(messages) + estimate_tokens(tools or []),
                 "output_tokens": estimate_tokens(content)}
        return {"content": content, "stop_reason": stop, "usage": usage}

    def _text(self, text, system, messages, tools, fault=None):
        r = self._respond([{"type": "text", "text": text}], system, messages, tools, "end_turn")
        r["_mock_fault"] = fault
        return r

    def _tool(self, calls, system, messages, tools, n):
        content = [{"type": "tool_use", "id": f"toolu_mock_{n}_{i}", "name": name, "input": inp}
                   for i, (name, inp) in enumerate(calls)]
        return self._respond(content, system, messages, tools, "tool_use")

    def create(self, system, messages, tools, context=None):
        qid, variant, run = context["qid"], context["variant"], context.get("run", 0)
        attempt = sum(1 for m in messages if m["role"] == "user" and isinstance(m["content"], str)) - 1
        results = [b["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], list)
                   for b in m["content"] if b.get("type") == "tool_result"]
        tool_numbers = [n for r in results for n in _numbers(r)]
        plan = PLANS[qid]
        if variant.startswith("v1"):
            obj = self._solve_sql(_db_from_prompt(system), qid)
        elif variant.startswith("v2"):
            calls = self._sql_calls(qid)
            if len(results) < len(calls):
                return self._tool(calls, system, messages, tools, len(results))
            obj = self._from_sql_results(qid, results)
        else:
            steps = self._v3_steps(qid)
            if len(results) < len(steps):
                nxt = steps[len(results)]
                if "{" in json.dumps(nxt[1]):                   # fill "{field}" from fields computed so far
                    done = self._v3_fields(qid, results)
                    nxt = (nxt[0], {k: (done.get(v[1:-1]) if isinstance(v, str) and v.startswith("{") else v)
                                    for k, v in nxt[1].items()})
                return self._tool([nxt], system, messages, tools, len(results))
            obj = self._from_v3_results(qid, results)
        obj, fault = _inject(obj, qid, variant, run, self.fault_rate, attempt, tool_numbers)
        return self._text(obj if isinstance(obj, str) else _final(obj), system, messages, tools, fault)

    # --- v1 and v2: the reference SQL
    def _solve_sql(self, con, qid):
        if qid == "B01":
            return _brief_obj({k: self._field_sql(con, ref) for k, ref in PLANS["B01"]["fields"].items()})
        p = PLANS[qid]
        return _answer_obj(_sql(con, p["sql"], p.get("shape", "scalar")))

    def _field_sql(self, con, ref):
        if isinstance(ref, str):
            p = PLANS[ref]
            return _sql(con, p["sql"], p.get("shape", "scalar"))
        return _sql(con, ref["sql"])

    def _sql_calls(self, qid):
        if qid == "B01":
            refs = PLANS["B01"]["fields"].values()
            return [("run_sql", {"query": (PLANS[r]["sql"] if isinstance(r, str) else r["sql"])}) for r in refs]
        return [("run_sql", {"query": PLANS[qid]["sql"]})]

    def _from_sql_results(self, qid, results):
        vals = []
        refs = list(PLANS["B01"]["fields"].items()) if qid == "B01" else [(None, qid)]
        for (k, ref), res in zip(refs, results[-len(refs):]):
            r = json.loads(res)
            shape = PLANS[ref].get("shape", "scalar") if isinstance(ref, str) else "scalar"
            rows = r.get("rows") or []
            vals.append([x[0] for x in rows] if shape == "list" else (rows[0][0] if rows else None))
        if qid == "B01":
            return _brief_obj(dict(zip(PLANS["B01"]["fields"], vals)))
        return _answer_obj(vals[0])

    # --- v3: skills and domain tools
    def _v3_plan_for(self, ref):
        return PLANS[ref]["v3"] if isinstance(ref, str) else ref["v3"]

    def _v3_steps(self, qid):
        if qid == "B01":
            steps = [("load_skill", {"name": "cash-position"})]
            for ref in PLANS["B01"]["fields"].values():
                steps += [tuple(c) for c in self._v3_plan_for(ref)["calls"]]
            return steps
        p = PLANS[qid]["v3"]
        return [("load_skill", {"name": p["skill"]})] + [tuple(c) for c in p["calls"]]

    def _v3_value(self, plan, res_json):
        r = json.loads(res_json)
        if r.get("missing_data") or "error" in r:
            return None
        v = _pick(r, plan["pick"])
        return -v if plan.get("negate") and v is not None else v

    def _v3_fields(self, qid, results):
        out, i = {}, 1
        for k, ref in PLANS["B01"]["fields"].items():
            plan = self._v3_plan_for(ref)
            n = len(plan["calls"])
            if i + n - 1 < len(results):
                out[k] = self._v3_value(plan, results[i + n - 1])
            i += n
        return out

    def _from_v3_results(self, qid, results):
        if qid == "B01":
            return _brief_obj(self._v3_fields(qid, results))
        return _answer_obj(self._v3_value(PLANS[qid]["v3"], results[-1]))


def _numbers(s):
    from variants.common import numbers_in
    return numbers_in(s)
