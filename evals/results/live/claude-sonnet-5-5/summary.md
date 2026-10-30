# live run

**LIVE MODEL RUN.**

Model: claude-sonnet-5-5. Runs per question: 5. Token counts are from the API; cost is priced as claude-sonnet-5-5 from config/models.yaml.

| metric | v1 | v2 | v3 |
|---|---|---|---|
| accuracy (all runs) | 1.0 | 1.0 | 1.0 |
| questions right every run | 33 | 33 | 33 |
| consistency: all runs agree | 0.97 | 1.0 | 1.0 |
| consistency: modal share | 0.994 | 1.0 | 1.0 |
| median numeric error % | 0.0 | 0.0 | 0.0 |
| mean numeric error % | 0.0 | 0.0 | 0.0 |
| abstentions correct | 20/20 | 20/20 | 20/20 |
| false abstentions | 0 | 0 | 0 |
| brief fields correct | 40/40 | 40/40 | 40/40 |
| brief unsupported $ figures | 0 | 1 | 0 |
| validator revisions | 0 | 0 | 0 |
| validator forced abstentions | 0 | 0 | 0 |
| input tokens (not cached) | 680 | 1266 | 1976 |
| cache read tokens | 15716719 | 982035 | 3143794 |
| cache write tokens | 2946 | 137798 | 281005 |
| output tokens | 155439 | 96073 | 115815 |
| cost USD | 3.1348 | 1.406 | 2.179 |
| cost per question USD | 0.01844 | 0.00827 | 0.01282 |
| cost per correct answer USD | 0.01844 | 0.00832 | 0.01282 |
| mean turns | 1 | 2.72 | 4.81 |
| median latency s | 3.216 | 5.204 | 7.558 |

## Outcomes

- v1: correct 165
- v2: correct 165
- v3: correct 165

## Why answers were wrong

- v1: none
- v2: brief: dollar figure not in the data 1
- v3: none

## Failures by brand

- fernwood-goods: v2: unsupported_number 1
