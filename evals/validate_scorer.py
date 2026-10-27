"""
Checks the scorer against mistakes of known types before trusting it with live results.

  python -m evals.validate_scorer [--n 5]

It runs the faulty mock and builds a table, by mistake type:
  - how many injected mistakes reached a final answer;
  - how many of those the scorer marked wrong (must be all);
  - how many the v3 validators stopped first.
Every clean answer must also be scored correct, so the table shows that the scorer
neither misses mistakes nor invents them.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evals.harness import ALL_IDS, run

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "results" / "scorer_validation.json"


def validate(n=5, write=True):
    recs = run("faulty", ["v1", "v2", "v3"], n, ALL_IDS, progress=False)
    t = defaultdict(lambda: {"reached_answer": 0, "scored_wrong": 0})
    clean = {"answers": 0, "scored_correct": 0}
    for r in recs:
        if r["forced_abstain"]:
            continue
        f = r["mock_fault"]
        if f:
            t[f]["reached_answer"] += 1
            t[f]["scored_wrong"] += int(not r["correct"])
        else:
            clean["answers"] += 1
            clean["scored_correct"] += int(r["correct"])
    v3_rev = sum(1 for r in recs if r["variant"] == "v3" and r["validator_events"])
    res = {"runs": len(recs), "by_fault": dict(t), "clean": clean, "v3_answers_sent_back": v3_rev,
           "v3_forced_abstentions": sum(r["forced_abstain"] for r in recs if r["variant"] == "v3"),
           "all_faults_caught": all(x["reached_answer"] == x["scored_wrong"] for x in t.values()),
           "no_false_flags": clean["answers"] == clean["scored_correct"]}
    if write:
        OUT.write_text(json.dumps(res, indent=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    res = validate(ap.parse_args().n)
    print(f"{'mistake type':<20}{'reached answer':>16}{'scored wrong':>14}")
    for k, v in sorted(res["by_fault"].items()):
        print(f"{k:<20}{v['reached_answer']:>16}{v['scored_wrong']:>14}")
    c = res["clean"]
    print(f"{'clean answers':<20}{c['answers']:>16}{c['scored_correct']:>14} scored correct")
    print(f"v3 validators sent back {res['v3_answers_sent_back']} answers and forced "
          f"{res['v3_forced_abstentions']} abstentions")
    print("scorer check:", "PASS" if res["all_faults_caught"] and res["no_false_flags"] else "FAIL")
    if not (res["all_faults_caught"] and res["no_false_flags"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
