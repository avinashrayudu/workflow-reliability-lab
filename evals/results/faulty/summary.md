# faulty run

**OFFLINE MOCK WITH INJECTED MISTAKES. Not model results: this run checks that the scorer and the v3 validators catch known mistake types.**

Model: mock-faulty. Runs per question: 3. Token counts are estimates (about 4 characters per token); cost is priced as claude-sonnet-5-5 from config/models.yaml (mock output is shorter than a real model writes, so read cost as a floor).

| metric | v1 | v2 | v3 |
|---|---|---|---|
| accuracy (all runs) | 0.768 | 0.707 | 0.808 |
| questions right every run | 14 | 13 | 18 |
| consistency: all runs agree | 0.424 | 0.394 | 0.545 |
| consistency: modal share | 0.778 | 0.758 | 0.838 |
| median numeric error % | 0.0 | 0.0 | 0.0 |
| mean numeric error % | 13.493 | 29.438 | 16.546 |
| abstentions correct | 10/12 | 7/12 | 12/12 |
| false abstentions | 3 | 4 | 4 |
| brief fields correct | 24/24 | 24/24 | 24/24 |
| brief unsupported $ figures | 0 | 0 | 0 |
| validator revisions | 0 | 0 | 8 |
| validator forced abstentions | 0 | 0 | 2 |
| input tokens | 3816792 | 212250 | 713430 |
| output tokens | 4086 | 13761 | 11493 |
| cost USD | 7.6744 | 0.5621 | 1.5418 |
| cost per question USD | 0.07524 | 0.00551 | 0.01512 |
| mean turns | 1 | 2 | 3.31 |
| median latency s | 0.025 | 0.0 | 0.001 |

## Outcomes

- v1: correct 76, false_abstention 3, format_error 3, missed_abstention 2, wrong_date 1, wrong_entity 3, wrong_number 10, wrong_set 1
- v2: correct 70, false_abstention 4, format_error 3, missed_abstention 4, wrong_date 1, wrong_entity 3, wrong_number 13, wrong_set 1
- v3: correct 80, false_abstention 4, wrong_count 1, wrong_date 3, wrong_entity 4, wrong_number 7

## Failures by brand

- bramble-pet: v2: format_error 1; v3: wrong_count 1
- copperleaf-tea: v1: missed_abstention 1; v2: missed_abstention 2, format_error 1
- fernwood-goods: v1: wrong_number 8, wrong_entity 2, false_abstention 1, wrong_date 1, format_error 2; v2: wrong_number 5, false_abstention 3, wrong_entity 3, wrong_date 1; v3: wrong_date 3, false_abstention 3, wrong_number 7, wrong_entity 3
- hollis-home: v2: wrong_number 2
- lark-and-pine: v2: wrong_number 1
- north-arc-outdoor: v1: wrong_number 2; v2: wrong_number 3
- portfolio: v1: false_abstention 2, wrong_entity 1, wrong_set 1; v2: wrong_set 1; v3: false_abstention 1, wrong_entity 1
- quillon-coffee: v1: format_error 1; v2: format_error 1, false_abstention 1
- saltmarsh-apparel: v1: missed_abstention 1; v2: missed_abstention 2, wrong_number 1
- tidewater-swim: v2: wrong_number 1
