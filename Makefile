# Built by Avinash Rayudu
PY ?= python3
N ?= 5
MODEL ?= claude-sonnet-5-5

.PHONY: demo truth mock faulty scorer report test dry-run live-check live data

demo: truth mock faulty scorer report test     ## offline, no API key needed

truth:                ## expected answers from data/csv, checked against forecast-health-monitor
	$(PY) -m truth.build_truth

mock:                 ## all 3 variants x 34 items x 3 runs on the offline oracle mock
	$(PY) -m evals.harness --mode mock --n 3

faulty:               ## same, with injected mistakes
	$(PY) -m evals.harness --mode faulty --n 3

scorer:               ## the scorer must catch every injected mistake
	$(PY) -m evals.validate_scorer --n 5

report:
	$(PY) -m reports.build_report

test:
	$(PY) -m pytest -q tests

dry-run:              ## token and dollar estimate for a live run, no calls
	$(PY) -m evals.harness --dry-run --n $(N) --model $(MODEL)

live-check:           ## is a live run ready? no model calls; prints READY or PENDING
	$(PY) -m evals.preflight --n $(N) --model $(MODEL)

MAX_USD ?= 40
live: live-check      ## real model calls; needs ANTHROPIC_API_KEY; stops at MAX_USD; never overwrites a live run
	$(PY) -m evals.harness --mode live --n $(N) --model $(MODEL) --max-usd $(MAX_USD)
	$(PY) -m reports.build_report

data:                 ## re-export the tables from a forecast-health-monitor checkout: make data B=../forecast-health-monitor
	$(PY) -m data.export_from_b $(B)
