"""
Runs every variant on every question N times and reports accuracy, consistency, numeric
error, abstention behaviour, cost and latency.

  python -m evals.harness --mode mock   --n 3     offline, deterministic (the default; make demo)
  python -m evals.harness --mode faulty --n 3     offline, with injected mistakes (scorer check)
  python -m evals.harness --mode live   --n 5     real model calls; needs ANTHROPIC_API_KEY
  python -m evals.harness --dry-run --n 5         token and dollar estimate for a live run, no calls

Results go to evals/results/<mode>/: runs.jsonl (every run), summary.json and summary.md.

Live runs are guarded so they can be published as they come:
  - a spend cap (--max-usd, default 40): the run stops before the next call once the priced cost
    of what has run reaches the cap, and the summary is marked incomplete;
  - no overwrite: a live result that already exists is never replaced unless --overwrite is given,
    so the first live run stays on record as it came out;
  - provenance: the summary records the git commit, whether the tree was clean, and hashes of the
    data, the questions and the answer key the run was scored against;
  - every finished run is appended to runs.partial.jsonl as it lands, so a crash loses nothing that
    was paid for, and --resume picks up where it stopped;
  - each model gets its own folder, evals/results/live/<model>/.

Live calls use prompt caching (agent/models.py) and can run in parallel (--workers). Each variant's
first call runs alone so the cache is written once before the rest read it.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import statistics as st
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent.models import CONFIG, AnthropicModel, price, price_usage
from agent.models import estimate_tokens
from agent.run import VARIANTS, load_variant, run_agent
from evals.score import QBRAND, QTYPE, score

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "evals" / "results"
QS = yaml.safe_load((ROOT / "truth" / "questions.yaml").read_text())
ALL_IDS = [q["id"] for q in QS["questions"]] + [QS["brief"]["id"]]


def question_text(qid):
    if qid == QS["brief"]["id"]:
        return QS["brief"]["q"]
    return next(q["q"] for q in QS["questions"] if q["id"] == qid)


def make_model(mode, model_name=None):
    if mode == "live":
        return AnthropicModel(model_name)
    from agent.mock import MockModel
    return MockModel("faulty" if mode == "faulty" else "oracle")


class BudgetReached(Exception):
    pass


def record_cost(r, model_name):
    """The API-priced cost of one run when the adapter recorded it (live), else priced from its tokens."""
    u = r["usage"]
    if u.get("cost_usd") is not None:
        return u["cost_usd"]
    c = price_usage(model_name, u)
    return c or 0.0


def spent(records, model_name):
    return sum(record_cost(r, model_name) for r in records)


def run(mode, variants, n, qids, model_name=None, progress=True, max_usd=None, model=None, stop=None, workers=1,
        prior=None, sink=None):
    """stop, if given, is a dict that gets {"budget_reached": True, "spent_usd": ...} when the cap stops the run.
    prior: records from an interrupted run of the same settings; their jobs are skipped and their cost counts.
    sink: called with each record as soon as it is scored (used to save live runs as they land)."""
    model = model or make_model(mode, model_name)
    records = list(prior or [])
    try:
        _run_all(model, mode, variants, n, qids, model_name, progress, max_usd, records, workers, sink)
    except BudgetReached:
        if stop is not None:
            stop.update(budget_reached=True, spent_usd=round(spent(records, model_name), 4))
        if progress:
            print(f"Spend cap of ${max_usd} reached after {len(records)} runs; stopping and writing a partial result.")
    order = {v: i for i, v in enumerate(variants)}
    qorder = {q: i for i, q in enumerate(qids)}
    records.sort(key=lambda r: (order.get(r["variant"], 99), qorder.get(r["qid"], 999), r["run"]))
    return records


def _run_all(model, mode, variants, n, qids, model_name, progress, max_usd, records, workers=1, sink=None):
    done = {(r["variant"], r["qid"], r["run"]) for r in records}
    lock = threading.Lock()
    specs, hit = {}, {"cap": False}

    def spec_for(vk, qid):
        with lock:
            if (vk, qid) not in specs:
                specs[(vk, qid)] = (load_variant(vk), None)
            v = specs[(vk, qid)][0]
        return v, v.build(question_text(qid))

    def one(job):
        vk, qid, i = job
        with lock:
            if hit["cap"] or (max_usd is not None and spent(records, model_name) >= max_usd):
                hit["cap"] = True
                return
        v, spec = spec_for(vk, qid)
        r = run_agent(model, spec, {"qid": qid, "variant": v.NAME, "run": i})
        s = score(qid, r["parsed"])
        rec = dict(variant=vk, qid=qid, run=i, brand=QBRAND[qid], qtype=QTYPE.get(qid, "brief"),
                   model=getattr(model, "model", mode), **s, usage=r["usage"], latency_s=r["latency_s"],
                   turns=r["turns"], tool_calls=len(r["tool_calls"]), validator_events=r["validator_events"],
                   forced_abstain=r["forced_abstain"], mock_fault=r["mock_fault"],
                   final_text=r["final_text"][-1500:])
        with lock:
            records.append(rec)
            if sink:
                sink(rec)
            if progress and mode == "live":
                print(f"  {vk} {qid} run {i}: {s['outcome']}  (spent ${spent(records, model_name):.2f})", flush=True)

    for vk in variants:
        jobs = [(vk, qid, i) for qid in qids for i in range(n) if (vk, qid, i) not in done]
        if not jobs:
            continue
        if workers <= 1:
            for job in jobs:
                one(job)
                if hit["cap"]:
                    raise BudgetReached()
            continue
        one(jobs[0])                                    # write the variant's cache once, alone
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one, jobs[1:]))
        if hit["cap"]:
            raise BudgetReached()


def error_type(r):
    """A plain-language label for a wrong answer, from the scorer's outcome; None when it is right."""
    if r["outcome"] == "correct":
        return None
    if r["qid"] == "B01":
        return "brief: dollar figure not in the data" if r.get("unsupported") else "brief: wrong field"
    oc = r["outcome"]
    if oc == "false_abstention":
        return "validator forced a refusal" if r.get("forced_abstain") else "refused an answerable question"
    if oc == "missed_abstention":
        return "answered when the data was missing"
    if oc == "format_error":
        return "ran out of turns" if "turn budget exhausted" in r.get("validator_events", []) else "no usable answer"
    if oc == "wrong_number":
        e = r.get("numeric_error")
        return "number off by under 1%" if e is not None and e < 0.01 else "number off by 1% or more"
    return oc.replace("_", " ")


def summarize(records, model_name):
    """model_name sets the prices used for cost; in mock modes that is the configured default model."""
    out = {}
    for vk in sorted({r["variant"] for r in records}):
        rs = [r for r in records if r["variant"] == vk]
        qrs = [r for r in rs if r["qid"] != "B01"]
        by_q = defaultdict(list)
        for r in qrs:
            by_q[r["qid"]].append(r)
        n = max(len(v) for v in by_q.values())
        consistent = [len({r["norm"] for r in v}) == 1 for v in by_q.values()]
        modal = [Counter(r["norm"] for r in v).most_common(1)[0][1] / len(v) for v in by_q.values()]
        all_right = [all(r["correct"] for r in v) for v in by_q.values()]
        maj_right = [sum(r["correct"] for r in v) > len(v) / 2 for v in by_q.values()]
        errs = [r["numeric_error"] for r in qrs if r["qtype"] == "money" and r["numeric_error"] is not None]
        ab = [r for r in qrs if r["qtype"] == "abstain"]
        nab = [r for r in qrs if r["qtype"] != "abstain"]
        brief = [r for r in rs if r["qid"] == "B01"]
        tin = sum(r["usage"]["input_tokens"] for r in rs)
        tout = sum(r["usage"]["output_tokens"] for r in rs)
        cw = sum(r["usage"].get("cache_creation_input_tokens", 0) for r in rs)
        cr = sum(r["usage"].get("cache_read_input_tokens", 0) for r in rs)
        cost = price(model_name, 0, 0) is not None and sum(record_cost(r, model_name) for r in rs)
        n_right = sum(r["correct"] for r in rs)
        out[vk] = {
            "runs_per_question": n, "questions": len(by_q),
            "accuracy": round(sum(r["correct"] for r in qrs) / len(qrs), 3),
            "questions_right_every_run": sum(all_right), "questions_right_by_majority": sum(maj_right),
            "consistency_all_runs_agree": round(sum(consistent) / len(consistent), 3),
            "consistency_modal_share": round(st.mean(modal), 3),
            "money_answers_scored": len(errs),
            "median_numeric_error_pct": round(100 * st.median(errs), 3) if errs else None,
            "mean_numeric_error_pct": round(100 * st.mean(errs), 3) if errs else None,
            "abstention_correct": f"{sum(r['correct'] for r in ab)}/{len(ab)}",
            "false_abstentions": sum(r["outcome"] == "false_abstention" for r in nab),
            "outcomes": dict(Counter(r["outcome"] for r in qrs)),
            "brief_fields_correct": f"{sum(r.get('fields_correct', 0) for r in brief)}/"
                                    f"{sum(r.get('fields', 8) for r in brief)}",
            "brief_dollar_figures": sum(r.get("dollar_figures", 0) for r in brief),
            "brief_unsupported_figures": sum(r.get("unsupported", 0) for r in brief),
            "validator_revisions": sum(bool(r["validator_events"]) for r in rs),
            "validator_forced_abstentions": sum(r["forced_abstain"] for r in rs),
            "error_types": dict(Counter(e for e in map(error_type, rs) if e)),
            "input_tokens": tin, "output_tokens": tout, "cache_write_tokens": cw, "cache_read_tokens": cr,
            "cost_usd": round(cost, 4) if cost is not False else None,
            "cost_per_question_usd": round(cost / len(rs), 5) if cost is not False else None,
            "correct_answers": n_right,
            "cost_per_correct_answer_usd": round(cost / n_right, 5) if cost is not False and n_right else None,
            "mean_turns": round(st.mean(r["turns"] for r in rs), 2),
            "median_latency_s": round(st.median(r["latency_s"] for r in rs), 3),
        }
    return out


def by_brand(records):
    t = defaultdict(lambda: defaultdict(Counter))
    for r in records:
        if r["outcome"] != "correct":
            t[r["brand"]][r["variant"]][r["outcome"]] += 1
    return {b: {v: dict(c) for v, c in vs.items()} for b, vs in t.items()}


def _sha(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def provenance():
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return ""
    return {"git_commit": git("rev-parse", "--short", "HEAD") or None,
            # clean = the code and inputs are committed; run outputs (results, the report) are ignored
            "tree_clean": git("status", "--porcelain", "--untracked-files=no", "--", ".",
                              ":(exclude)evals/results", ":(exclude)reports") == "",
            "data_sha": _sha(list((ROOT / "data" / "csv").glob("*.csv"))),
            "questions_sha": _sha([ROOT / "truth" / "questions.yaml"]),
            "answer_key_sha": _sha([ROOT / "truth" / "answers.json"])}


def live_dir(model_name, root=None):
    return (root or RES) / "live" / model_name


def write(mode, records, model_name, n, price_model=None, overwrite=False, complete=True, spent_usd=None,
          root=None, subdir=None):
    price_model = price_model or model_name
    d = (root or RES) / (subdir or mode)
    if mode == "live" and (d / "summary.json").exists() and not overwrite:
        raise SystemExit(f"{d} already holds a live run. It is kept as it came out; pass --overwrite to replace it, "
                         "or move it aside first.")
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "runs.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")
    summ = {"mode": mode, "model": model_name, "runs_per_question": n,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tokens_are_estimates": mode != "live", "priced_as": price_model,
            "complete": complete, "spent_usd": spent_usd, "provenance": provenance(),
            "variants": summarize(records, price_model),
            "failures_by_brand": by_brand(records)}
    (d / "summary.json").write_text(json.dumps(summ, indent=1))
    (d / "summary.md").write_text(render_md(summ))
    return summ


BANNER = {"mock": "OFFLINE MOCK (oracle). Not model results: a perfect score shows every question is answerable "
                  "through each variant's interface and the reference solutions agree with the truth file.",
          "faulty": "OFFLINE MOCK WITH INJECTED MISTAKES. Not model results: this run checks that the scorer and the "
                    "v3 validators catch known mistake types.",
          "live": "LIVE MODEL RUN."}


def render_md(s):
    L = [f"# {s['mode']} run", "", f"**{BANNER[s['mode']]}**", ""]
    if not s.get("complete", True):
        L += [f"**INCOMPLETE: the spend cap stopped this run at ${s.get('spent_usd')}. Scores cover only the runs "
              "that finished.**", ""]
    L += [
         f"Model: {s['model']}. Runs per question: {s['runs_per_question']}. "
         f"Token counts are {'estimates (about 4 characters per token)' if s['tokens_are_estimates'] else 'from the API'}; "
         f"cost is priced as {s['priced_as']} from config/models.yaml"
         f"{' (mock output is shorter than a real model writes, so read cost as a floor)' if s['tokens_are_estimates'] else ''}.",
         "", "| metric | " + " | ".join(s["variants"]) + " |", "|---|" + "---|" * len(s["variants"])]
    rows = [("accuracy (all runs)", "accuracy"), ("questions right every run", "questions_right_every_run"),
            ("consistency: all runs agree", "consistency_all_runs_agree"),
            ("consistency: modal share", "consistency_modal_share"),
            ("median numeric error %", "median_numeric_error_pct"), ("mean numeric error %", "mean_numeric_error_pct"),
            ("abstentions correct", "abstention_correct"), ("false abstentions", "false_abstentions"),
            ("brief fields correct", "brief_fields_correct"), ("brief unsupported $ figures",
                                                              "brief_unsupported_figures"),
            ("validator revisions", "validator_revisions"), ("validator forced abstentions",
                                                            "validator_forced_abstentions"),
            ("input tokens (not cached)", "input_tokens"), ("cache read tokens", "cache_read_tokens"),
            ("cache write tokens", "cache_write_tokens"), ("output tokens", "output_tokens"), ("cost USD", "cost_usd"),
            ("cost per question USD", "cost_per_question_usd"),
            ("cost per correct answer USD", "cost_per_correct_answer_usd"), ("mean turns", "mean_turns"),
            ("median latency s", "median_latency_s")]
    for label, k in rows:
        L.append(f"| {label} | " + " | ".join(str(v.get(k)) for v in s["variants"].values()) + " |")
    L += ["", "## Outcomes", ""]
    for vk, v in s["variants"].items():
        L.append(f"- {vk}: " + ", ".join(f"{k} {n}" for k, n in sorted(v["outcomes"].items())))
    L += ["", "## Why answers were wrong", ""]
    for vk, v in s["variants"].items():
        et = v.get("error_types") or {}
        L.append(f"- {vk}: " + (", ".join(f"{k} {n}" for k, n in sorted(et.items(), key=lambda x: -x[1]))
                                or "none"))
    L += ["", "## Failures by brand", ""]
    for b, vs in sorted(s["failures_by_brand"].items()):
        L.append(f"- {b}: " + "; ".join(f"{v}: " + ", ".join(f"{k} {n}" for k, n in c.items())
                                         for v, c in sorted(vs.items())))
    if not s["failures_by_brand"]:
        L.append("- none")
    return "\n".join(L) + "\n"


def dry_run(n, variants, qids, model_name):
    """Uses the oracle mock's token accounting for the real prompts. Live runs that take
    more turns than the reference solution cost more, so read this as a floor."""
    recs = run("mock", variants, 1, qids, progress=False)
    print(f"Estimated tokens for a live run: {len(qids)} questions x {n} runs, model {model_name}")
    total = total_cached = 0.0
    for vk in variants:
        rs = [r for r in recs if r["variant"] == vk]
        tin = n * sum(r["usage"]["input_tokens"] for r in rs)
        tout = n * sum(r["usage"]["output_tokens"] for r in rs)
        # the reference solution writes little; budget ~400 output tokens per turn for a real model
        tout_real = n * sum(400 * r["turns"] for r in rs)
        c = price(model_name, tin, tout_real)
        # with caching, every call reads the variant's system prompt and tools from cache after the first
        v = load_variant(vk)
        sp = v.build(question_text(qids[0]))
        prefix = estimate_tokens(sp["system"]) + (estimate_tokens(sp["tools"]) if sp["tools"] else 0)
        calls = n * sum(r["turns"] for r in rs)
        cached = price(model_name, max(0, tin - calls * prefix), tout_real, 3 * prefix, calls * prefix)
        total_cached += cached or 0
        total += c or 0
        print(f"  {vk}: ~{tin:,} input tokens, ~{tout_real:,} output tokens (budgeted), "
              f"~${c:,.2f}" if c is not None else f"  {vk}: ~{tin:,} input tokens (no price configured)")
    print(f"  total: ~${total:,.2f} without caching; ~${total_cached:,.2f} with prompt caching "
          f"(a floor: a real model takes more turns than the reference solutions)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="mock", choices=["mock", "faulty", "live"])
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--variants", default="v1,v2,v3")
    ap.add_argument("--questions", default="all")
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-usd", type=float, default=40.0, help="live mode: stop before spending more than this")
    ap.add_argument("--overwrite", action="store_true", help="live mode: replace an existing live result")
    ap.add_argument("--workers", type=int, default=1, help="calls in parallel")
    ap.add_argument("--resume", action="store_true", help="live mode: continue from runs.partial.jsonl")
    ap.add_argument("--out", default=None, help="results folder under evals/results (default: mode, or live/<model>)")
    a = ap.parse_args()
    variants = a.variants.split(",")
    for v in variants:
        assert v in VARIANTS, v
    qids = ALL_IDS if a.questions == "all" else a.questions.split(",")
    model_name = a.model or CONFIG["default_model"]
    if a.dry_run:
        return dry_run(a.n, variants, qids, model_name)
    subdir = a.out or (f"live/{model_name}" if a.mode == "live" else a.mode)
    d = RES / subdir
    prior, sink = None, None
    if a.mode == "live":
        if (d / "summary.json").exists() and not a.overwrite:
            raise SystemExit(f"{d.relative_to(ROOT)} already holds a live run; pass --overwrite to replace it.")
        d.mkdir(parents=True, exist_ok=True)
        part = d / "runs.partial.jsonl"
        if a.resume and part.exists():
            prior = [json.loads(x) for x in part.read_text().splitlines() if x.strip()]
            print(f"Resuming: {len(prior)} runs already done, ${spent(prior, model_name):.2f} already spent.")
        elif part.exists():
            raise SystemExit(f"{part.relative_to(ROOT)} holds an interrupted run; pass --resume to continue it.")
        fh = open(part, "a")

        def sink(rec):
            fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
    stop = {}
    recs = run(a.mode, variants, a.n, qids, model_name, max_usd=a.max_usd if a.mode == "live" else None, stop=stop,
               workers=a.workers, prior=prior, sink=sink)
    label = model_name if a.mode == "live" else {"mock": "mock-oracle", "faulty": "mock-faulty"}[a.mode]
    write(a.mode, recs, label, a.n, price_model=model_name, overwrite=a.overwrite,
          complete=not stop.get("budget_reached"), spent_usd=round(spent(recs, model_name), 4) if a.mode == "live" else None,
          subdir=subdir)
    if a.mode == "live":
        fh.close()
        (d / "runs.partial.jsonl").unlink()
    print((d / "summary.md").read_text())


if __name__ == "__main__":
    main()
