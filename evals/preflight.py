"""
Checks that a live run is ready, without making any model call:

  python -m evals.preflight [--model claude-sonnet-5-5] [--n 5]

It verifies that the answer key still matches the data and the questions, that the model has
a price in config/models.yaml (so the spend cap can work), that no live result would be
overwritten, and that an API key is set. It never prints the key. It prints the estimated cost
and ends with READY, or PENDING with the reason.

Built by Avinash Rayudu.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from agent.models import CONFIG, price
from evals.harness import ALL_IDS, RES, ROOT, dry_run, provenance


def checks(model: str, env=os.environ) -> list[tuple[str, bool, str]]:
    out = []
    from truth.build_truth import Truth
    T = Truth()
    fresh = json.loads(json.dumps({"answers": T.answers(), "brief_support": T.brief_support()}, default=str))
    saved = json.loads((ROOT / "truth" / "answers.json").read_text())
    same = fresh == saved
    out.append(("answer key matches the data and questions", same,
                "truth/answers.json is current" if same else "run make truth, then re-check"))
    priced = price(model, 0, 0) is not None
    out.append((f"{model} has a price in config/models.yaml", priced,
                "the spend cap can price every call" if priced else "add its prices first"))
    free = not (RES / "live" / "summary.json").exists()
    out.append(("no live result would be overwritten", free,
                "evals/results/live/ is empty" if free else "a live run is already on record"))
    key = bool(env.get("ANTHROPIC_API_KEY"))
    out.append(("ANTHROPIC_API_KEY is set", key, "set (not shown)" if key else "not set"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=CONFIG["default_model"])
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args(argv)
    res = checks(a.model)
    for name, ok, note in res:
        print(f"  [{'ok' if ok else '--'}] {name}: {note}")
    p = provenance()
    print(f"  code at {p['git_commit']} ({'clean tree' if p['tree_clean'] else 'uncommitted changes'}); "
          f"data {p['data_sha']}, questions {p['questions_sha']}, answer key {p['answer_key_sha']}")
    dry_run(a.n, ["v1", "v2", "v3"], ALL_IDS, a.model)
    failed = [f"{n.split(' has ')[0] if ' has ' in n else n} ({note})" for n, ok, note in res if not ok]
    if failed:
        print("PENDING: " + "; ".join(failed))
        return 1
    print(f"READY: run  make live N={a.n} MODEL={a.model}  (spend cap $40 unless MAX_USD is set)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
