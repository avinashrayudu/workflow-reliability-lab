# Design notes

## The question this lab asks

A finance workflow is only useful if it gives the same right number every time, and if it says "I can't tell" when a brand's data is incomplete.

Every brand's data is incomplete in its own way. So the lab holds the job constant and changes only how the work is split between the model and code:

| Variant | The model's job | Code's job |
|---|---|---|
| v1 single prompt | read about 37K tokens of tables, find rows, add them up | nothing |
| v2 SQL tools | write queries, read results | run the queries (read-only) |
| v3 skills + validators | pick a skill and a tool, copy a number | compute each quantity, check provenance and coverage |

## What I expect, before any live run

These are hypotheses, not results. `make live` tests them.

1. **v1 will make arithmetic errors on multi-row sums.** Examples are closing cash (13 weekly sums), 3-week variances and portfolio counts. Its errors should be small percentages, not wild numbers. It may also answer the gap questions instead of abstaining, because the forecast column sits right next to the missing actual.
2. **v2 will mostly be right or badly wrong.** Its typical failures will be a wrong filter: the wrong week index, forgetting `is_cash = 1`, or including `ad_spend_accrual`. Each of those gives a wrong number with confidence. Consistency across runs should be lower than v3's, because a query can be written several ways.
3. **v3 will be the most consistent.** Its failures will be routing failures, such as the wrong basis (forecast vs roll-forward) or the wrong tool. The coverage check should make its abstentions near perfect. The open question is false abstentions, which happen when a model reads a gap in one source as a reason to refuse everything.
4. **Cost per question will run v1 > v3 > v2.** That order comes from the token counts of the real prompts (see the README). Latency should run v3 > v2 > v1 by turns.

## Eval design choices

- **Exact answers only.** Every question has one number, date, ID, count or set. A money answer counts as right within max($1, 0.05%). There is no partial credit and no model grader.
- **Two independent truths.** One is pandas in `truth/build_truth.py`. The other is the reference SQL and tool calls in `evals/mock_plans.yaml`. A test requires them to agree on all 34 items, through all three variants' interfaces.
- **Planted gaps:** a missing week, an AP source that isn't connected, and SKU refunds that aren't connected. Four questions require an abstention. Two control questions require an answer for the same brands, so a workflow that refuses everything scores badly.
- **Consistency is scored separately from accuracy.** A workflow can be right 80% of the time and still give three different answers to the same question over three runs. A finance team cannot use that.
- **The brief is scored two ways.** Its eight fields must be exact, and every dollar figure in its prose has to trace to the data. This catches the "plausible number" failure, where a figure reads fine and is invented.

## What the mock can and cannot say

The oracle mock proves three things: every question is answerable through each variant's interface, the reference solutions match the truth, and the token footprint of each design. The faulty mock proves the scorer catches known mistakes.

Neither says anything about how a model performs. Those numbers come only from `make live`.

Built by Avinash Rayudu.
