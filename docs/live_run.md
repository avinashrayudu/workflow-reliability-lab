# The live run: status and runbook

**Status: pending.** No language model has been scored yet. The run needs an Anthropic API key, which this project
does not have yet. Everything in `evals/results/` today comes from the offline mock, and every page that shows those
numbers labels them "harness-validated, not live".

## What is ready

| Piece | State |
|---|---|
| 33 graded questions plus the brief, with a computed answer key | done, checked against forecast-health-monitor |
| Three variants behind one agent loop | done; the loop is tested with a scripted model |
| Live adapter (`agent/models.py`) | done; the request shape is tested without a network call |
| Scorer | done; it caught 121 of 121 planted mistakes and passed 384 of 384 clean answers |
| Cost estimate | about $20 for 5 runs of every variant on Sonnet 5.5 (`make dry-run`), a floor |
| Preflight (`make live-check`) | done; prints READY or PENDING and never prints the key |
| Spend cap | `MAX_USD` (default $40, twice the estimate). The run stops before the next call once the priced cost reaches the cap, so it can go over by at most one call, and the summary is marked incomplete. |
| No overwrite | the first live result is kept as it came out; replacing it needs `--overwrite` |
| Provenance | each summary records the git commit, whether the tree was clean, and hashes of the data, questions and answer key |

## How to run it

```
pip install -r requirements.txt
make live-check                                    # expect PENDING until a key is set
export ANTHROPIC_API_KEY=...                       # never commit it
make live-check                                    # expect READY
make live N=5 MODEL=claude-sonnet-5-5 MAX_USD=40   # about 30 to 60 minutes
```

Run it on a clean tree so the commit hash in the summary points at the code that produced it.

## What gets published, and how

1. Commit `evals/results/live/` as it came out (`runs.jsonl`, `summary.json`, `summary.md`) in its own commit:
   `results: first live run, Sonnet 5.5, N=5`.
2. Rebuild the report (`make report`, which `make live` already runs). The live section goes on top; the mock
   sections stay below it, labeled as before.
3. Update the README status, the case study and the site card in a second commit, quoting the summary's numbers
   exactly, including any variant that loses and any prediction in `docs/design_notes.md` that turned out wrong.
4. If the spend cap stopped the run, publish it marked incomplete, or rerun with a higher cap and say so.

Nothing in the README or on the site changes from "harness-validated, not live" until step 1 is in the history.
