# live run

**LIVE MODEL RUN.**

Model: claude-sonnet-5-5. Runs per question: 2. Token counts are from the API; cost is priced as claude-sonnet-5-5 from config/models.yaml.

| metric | v1 | v2 | v3 |
|---|---|---|---|
| accuracy (all runs) | 0.75 | 1.0 | 1.0 |
| questions right every run | 1 | 2 | 2 |
| consistency: all runs agree | 0.5 | 1.0 | 1.0 |
| consistency: modal share | 0.75 | 1.0 | 1.0 |
| median numeric error % | 0.0 | 0.0 | 0.0 |
| mean numeric error % | 0.0 | 0.0 | 0.0 |
| abstentions correct | 0/0 | 0/0 | 0/0 |
| false abstentions | 0 | 0 | 0 |
| brief fields correct | 0/0 | 0/0 | 0/0 |
| brief unsupported $ figures | 0 | 0 | 0 |
| validator revisions | 0 | 0 | 0 |
| validator forced abstentions | 0 | 0 | 0 |
| input tokens (not cached) | 16 | 36 | 48 |
| cache read tokens | 277295 | 27655 | 70955 |
| cache write tokens | 92539 | 7291 | 14799 |
| output tokens | 7843 | 2860 | 2705 |
| cost USD | 0.3375 | 0.0497 | 0.0712 |
| cost per question USD | 0.08438 | 0.01242 | 0.01781 |
| cost per correct answer USD | 0.11251 | 0.01242 | 0.01781 |
| mean turns | 1 | 3.5 | 5 |
| median latency s | 14.442 | 8.16 | 8.41 |

## Outcomes

- v1: correct 3, format_error 1
- v2: correct 4
- v3: correct 4

## Why answers were wrong

- v1: no usable answer 1
- v2: none
- v3: none

## Failures by brand

- fernwood-goods: v1: format_error 1
