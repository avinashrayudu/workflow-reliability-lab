# workflow-reliability-lab

**Why it matters.** Before a finance agent's number reaches a founder, someone has to know how often it is right,
whether it gives the same answer twice, and whether it says "I can't tell" when a brand's data is missing. This is
the harness that measures that, so a design choice is made on evidence instead of a demo.
**What it is.** One finance workflow, Fernwood Goods' Monday Cash Brief, built three ways: one big prompt, SQL tools,
and skills with validators. A harness runs each version N times on the same 33 graded questions plus the brief, and
reports accuracy, consistency, numeric error, abstention and cost.
**Best result so far (harness-validated, not live).** The scorer caught all 121 mistakes planted across 12 types and
passed all 384 clean answers, and every question is answerable through every variant. **No model has been scored
yet: the live run is pending an API key.**
**See it.** [Reliability report](https://avinashrayudu.github.io/workflow-reliability-lab/reports/reliability.html) ·
[case study](https://www.avinashrayudu.com/work/workflow-reliability-lab/) ·
[live-run runbook](docs/live_run.md) · [finance concepts](docs/finance_concepts.md)

Built by Avinash Rayudu. Every brand and number here is synthetic.

## Status: live run pending

There are no model scores yet. Everything committed in `evals/results/` comes from the offline mock, which is
deterministic and is not a language model. The live run needs an Anthropic API key, which this project does not have
yet. Everything else is ready, and [docs/live_run.md](docs/live_run.md) says what will be published and how.

```
pip install -r requirements.txt
make live-check                                   # READY or PENDING; no model calls, never prints the key
make dry-run N=5                                  # token and dollar estimate, no calls
ANTHROPIC_API_KEY=... make live N=5 MODEL=claude-sonnet-5-5 MAX_USD=40
```

The dry run puts a 5-run pass of all three variants at about **$20 on Sonnet 5.5**, using the prices in
`config/models.yaml` (checked 2026-10-27). Treat that as a floor: a real model may take more turns than the reference
solutions. `make live` runs the preflight first, stops before the next call once spending reaches `MAX_USD` (and
marks the result incomplete), refuses to overwrite a live result already on record, and stamps the summary with the
git commit and hashes of the data, questions and answer key. When the live run is in, this section, the report and
the case study will show its scores as they come, including any variant that loses.

## What the offline run does prove

`make demo` runs all of this end to end in about 16 seconds:

1. **Every question is answerable through every variant, and the answer key is right.** The reference solutions get 33 of 33 questions plus all 8 brief fields through each variant's own interface. For v1, that means rebuilding the tables from the CSV text in the prompt. These solutions are SQL and tool calls in `evals/mock_plans.yaml`. They are a second computation, independent of the pandas answer key in `truth/build_truth.py`, and a test requires the two to agree. The key also reproduces what forecast-health-monitor printed for the same data: a **$194,498** low point in the week of Nov 16, and a **$125,000** draw. That draw is the week-0 figure (the smallest $25,000 step that holds the buffer before any actuals); the Nov 16 brief in forecast-health-monitor calls for $225,000 because refunds have since deepened the trough and the draw adds a cushion.
2. **The scorer catches mistakes of every type I injected.** The faulty mock planted 121 mistakes across 12 types:
   - wrong sign, wrong scale, 3% drift, a neighboring number;
   - a week off by one, the wrong SKU or brand, an off-by-one count, a dropped list item;
   - missed abstention, false abstention, broken format, an invented dollar figure in the brief.

   All 121 were scored wrong, and all 384 clean answers were scored right. Separately, the v3 validators sent 15 injected answers back and forced 5 abstentions before scoring.
3. **What each design costs per question,** measured on the real prompts at about 4 characters per token:

| Variant | Input tokens per question | Calls per question | Cost per question at Sonnet 5.5 prices |
|---|---:|---:|---:|
| v1 single prompt | ~37,400 | 1 | ~$0.075 |
| v2 SQL tools | ~2,100 | 2 | ~$0.006 |
| v3 skills + validators | ~6,800 | ~3.2 | ~$0.015 |

These are reference-solution turn counts with very short outputs, so live costs will be higher.

## The three variants

| | What the model gets | Where the arithmetic happens |
|---|---|---|
| **v1** `variants/v1_single_prompt` | Every table as CSV in the prompt (about 37K tokens), and no tools | in the model |
| **v2** `variants/v2_sql_tools` | The schema and a read-only `run_sql` tool | in SQL the model writes |
| **v3** `variants/v3_skills_validators` | A skill index; `load_skill` returns a SKILL.md; nine domain tools such as `cash_path`, `variance`, `bills` and `credit_math` | in code; the model picks the tool and copies the number |

All three share the same definitions (`config/definitions.md`) and the same answer format.

v3 also runs two validators before it accepts an answer:
- **Provenance:** every number in the answer, and every dollar figure in the brief, must appear in a tool result from that run.
- **Coverage:** if any tool reported missing data, the answer must be an abstention.

A failed check goes back to the model once. A second failure becomes an abstention.

## The eval set

`truth/questions.yaml` holds 33 questions and the brief. Every expected answer is computed, none are typed by hand.

- **Fernwood Goods (18 questions):** low point and its week, gap and draw, actual closing cash, variances, the SKU behind the refund overrun, the largest bill this week, an early-pay discount and its deadline, interest, paydown vs sweep.
- **Other brands (6):** a freight overcharge, a Meta overspend, an Amazon settlement, wholesale totals, payroll count, sales tax.
- **Portfolio (3):** how many brands go under their buffer, which brand is tightest, which brands have no wholesale.
- **Abstentions (4):** three gaps are planted on purpose.
  - Copperleaf Tea's week of Nov 9 never arrived.
  - Saltmarsh Apparel's AP bills are not connected.
  - Lark & Pine's SKU refunds are not connected.
- **Controls (2):** the same brands, but on questions the data can answer, so refusing everything is penalized.
- **The brief:** 8 fields scored exactly. Every dollar figure in its narrative must trace to Fernwood's data.

**Scoring** (`evals/score.py`):
- Money is right within max($1, 0.05%). Dates, IDs, counts and sets must match exactly.
- Abstaining on an answerable question counts as wrong.
- **Consistency** is the share of questions where all N runs give the same answer.
- **Numeric error** is |answer − truth| / |truth| on money answers.

## Repository

```
data/              the 7 tables (CSV + SQLite), exported from forecast-health-monitor; snapshot Mon Nov 16, 2026
config/            definitions every variant receives; model, prices, temperature
truth/             the questions and the pandas answer key (truth/answers.json)
variants/          v1, v2, v3
skills/            6 SKILL.md files for v3
agent/run.py       the tool-use loop (Messages API shapes; validators; send-back)
agent/models.py    live adapter (standard-library HTTP) and token/cost accounting
agent/mock.py      the offline oracle and faulty mocks, and what they are for
evals/             harness, preflight, scorer, scorer check, reference solutions, results
reports/           reliability.html: scorecard, question-by-question grid, failure taxonomy by brand
docs/design_notes.md   what each variant is expected to get wrong, written before any live run
docs/live_run.md   the live run: what is ready, how to run it, what gets published
tests/             19 tests: answer-key agreement, scorer catches, read-only SQL, validator logic,
                   the agent loop with a scripted model, the live request shape (no network),
                   and the live-run guards (spend cap, no overwrite, provenance, preflight)
```

## Why these numbers

Every threshold, in plain language, with where it comes from.

| Setting | Value | In plain language | Where it comes from |
|---|---|---|---|
| Money tolerance | the larger of $1 or 0.05% | Rounding to the dollar is fine; anything bigger is a different number. | Set by hand. On a $194,498 low point, 0.05% is about $97. |
| Runs per variant | N = 5 | Ask the same question five times to see whether the answer changes. | Enough to see inconsistency; consistency is scored separately from accuracy. |
| Temperature | 1.0 | The model's default setting, which is how people actually use it. | `config/models.yaml`; change it there. |
| Abstentions | 4 required, 2 controls | The workflow must refuse when data is missing, and must not refuse when it isn't. | The controls ask about the same brands on answerable questions, so refusing everything scores badly. |
| Spend cap | $40 by default | Twice the estimated cost, so a run that loops cannot run up a bill. | `MAX_USD` in the Makefile; the run can go over by at most one call. |

## Limits

- **The mock is not a model.** Its accuracy shows the questions can be answered and the plumbing works, and nothing more.
- **I wrote the questions and the gaps,** so they test the failure modes I thought of.
- **One snapshot, one brief, 10 synthetic brands.**
- **Temperature 1.0 by default.** Consistency is measured at the setting people actually use. Change it in `config/models.yaml`.
- **Mock token counts are estimates.** Live runs record the API's own usage.

## Where this fits at Highbeam

My reading of Highbeam's public Luma pages and the AI Implementation Associate posting. This project is not
affiliated with Highbeam and uses no Highbeam data.

| This project | Highbeam / Luma workflow it would show | The role's work it rehearses |
|---|---|---|
| One brief built three ways and graded on exact answers | The Analyst agent, which answers finance questions on demand and writes live cash reports | Prompting the platform, evaluating outputs, tuning behavior |
| Skills with validators: every number must come from a tool | Luma's approach of running code against the data instead of letting a model read it directly | Building the skills and workflows the platform uses |
| Planted gaps the workflow must refuse | Outputs that are "accurate, secure, explainable, and verifiable" | Knowing when a brand's setup is incomplete |
| Cost per question for each design | | Choosing a design on evidence |

Sources: [Highbeam Intelligence](https://www.highbeam.com/blog/expert-finance-agents-for-consumer-brands-highbeam-intelligence),
[Building Luma](https://highbeam.com/blog/building-luma-an-approach-to-transform-financial-work-with-applied-ai).

## Finance concepts

The questions are about cash: the low point, the draw, variances, bills and discounts, sales tax. One planted gap is
"AP bills not connected", where the right answer is to abstain. [docs/finance_concepts.md](docs/finance_concepts.md)
covers AP and AR, cash vs accrual and the three-way match across all three projects.

## How I built this

I built this with Claude Code, Anthropic's coding agent. I chose what to test and set the rules: compute every
expected answer instead of typing it, plant gaps the workflow must refuse, write the predictions down before any live
run, label mock results as mock everywhere, and never publish a model score that a committed live run did not
produce. Claude Code wrote most of the code, tests and first drafts of the docs under that direction and ran the
offline harness. I read the results and decided what changed. [CHANGELOG.md](CHANGELOG.md) shows the order things
happened in.

## Why I built this

At Zacao Chocolate, I tested a Retell voice agent against 30 adversarial scenarios before it took real calls. This applies the same habit to a finance workflow: decide what "right" means before the first run, plant the cases where it should refuse, and count how often it gives the same answer twice.

Built by Avinash Rayudu. MIT License.
