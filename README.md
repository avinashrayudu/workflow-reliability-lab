# workflow-reliability-lab

**What it is.** One finance workflow, Fernwood Goods' Monday Cash Brief, built three ways: one big prompt, SQL tools,
and skills with validators. A harness runs each version N times on the same 33 graded questions plus the brief, and
reports accuracy, consistency, numeric error, abstention and cost.
**Best result so far (harness-validated, not live).** The scorer caught all 121 mistakes planted across 12 types and
passed all 384 clean answers, and every question is answerable through every variant. No model has been scored yet.
**See it.** [Reliability report](https://avinashrayudu.github.io/workflow-reliability-lab/reports/reliability.html) ·
[case study](https://www.avinashrayudu.com/work/workflow-reliability-lab/)

Built by Avinash Rayudu. Every brand and number here is synthetic.

## Status: harness-validated, not live

There are no model scores yet. Everything committed in `evals/results/` comes from the offline mock, which is
deterministic and is not a language model. The live run is one command and costs about $20:

```
pip install -r requirements.txt
make dry-run N=5                                  # token and dollar estimate, no calls
ANTHROPIC_API_KEY=... make live N=5 MODEL=claude-sonnet-5-5
```

The dry run puts a 5-run pass of all three variants at about **$20 on Sonnet 5.5**, using the prices in
`config/models.yaml` (checked 2026-10-27). Treat that as a floor: a real model may take more turns than the reference
solutions. When the live run is in, this section, the report and the case study will show its scores as they come,
including any variant that loses.

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
evals/             harness, scorer, scorer check, reference solutions, results
reports/           reliability.html: scorecard, question-by-question grid, failure taxonomy by brand
docs/design_notes.md   what each variant is expected to get wrong, written before any live run
tests/             15 tests: answer-key agreement, scorer catches, read-only SQL, validator logic,
                   the agent loop with a scripted model, the live request shape (no network)
```

## Why these numbers

| Setting | Value | Why |
|---|---|---|
| Money tolerance | the larger of $1 or 0.05% | Rounding to the dollar is fine; anything bigger is a different number. |
| Runs per variant | N = 5 | Enough to see whether a variant gives the same answer twice; consistency is scored separately from accuracy. |
| Temperature | 1.0 | Consistency is measured at the setting people actually use. |
| Abstentions | 4 required, 2 controls | The controls ask about the same brands on answerable questions, so a variant that refuses everything scores badly. |

## Limits

- **The mock is not a model.** Its accuracy shows the questions can be answered and the plumbing works, and nothing more.
- **I wrote the questions and the gaps,** so they test the failure modes I thought of.
- **One snapshot, one brief, 10 synthetic brands.**
- **Temperature 1.0 by default.** Consistency is measured at the setting people actually use. Change it in `config/models.yaml`.
- **Mock token counts are estimates.** Live runs record the API's own usage.

## Why I built this

At Zacao Chocolate, I tested a Retell voice agent against 30 adversarial scenarios before it took real calls. This applies the same habit to a finance workflow: decide what "right" means before the first run, plant the cases where it should refuse, and count how often it gives the same answer twice.

Built by Avinash Rayudu. MIT License.
