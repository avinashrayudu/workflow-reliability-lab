# live run

**LIVE MODEL RUN.**

Model: claude-haiku-5-5. Runs per question: 5. Token counts are from the API; cost is priced as claude-haiku-5-5 from config/models.yaml.

| metric | v1 | v2 | v3 |
|---|---|---|---|
| accuracy (all runs) | 0.915 | 0.982 | 1.0 |
| questions right every run | 27 | 31 | 33 |
| consistency: all runs agree | 0.879 | 0.909 | 1.0 |
| consistency: modal share | 0.976 | 0.976 | 1.0 |
| median numeric error % | 0.0 | 0.0 | 0.0 |
| mean numeric error % | 3.056 | 0.543 | 0.0 |
| abstentions correct | 20/20 | 20/20 | 20/20 |
| false abstentions | 0 | 1 | 0 |
| brief fields correct | 40/40 | 40/40 | 40/40 |
| brief unsupported $ figures | 2 | 3 | 0 |
| validator revisions | 0 | 0 | 2 |
| validator forced abstentions | 0 | 0 | 0 |
| input tokens (not cached) | 680 | 1202 | 1980 |
| cache read tokens | 15624291 | 987740 | 3089531 |
| cache write tokens | 95374 | 319970 | 461047 |
| output tokens | 268160 | 165104 | 154435 |
| cost USD | 0.3023 | 0.1325 | 0.1659 |
| cost per question USD | 0.00178 | 0.00078 | 0.00098 |
| cost per correct answer USD | 0.00195 | 0.0008 | 0.00098 |
| mean turns | 1 | 2.54 | 4.81 |
| median latency s | 3.045 | 4.803 | 5.826 |

## Outcomes

- v1: correct 151, format_error 10, wrong_date 1, wrong_number 3
- v2: correct 162, false_abstention 1, wrong_number 2
- v3: correct 165

## Why answers were wrong

- v1: no usable answer 10, number off by 1% or more 2, wrong date 1, number off by under 1% 1, brief: dollar figure not in the data 1
- v2: number off by 1% or more 2, brief: dollar figure not in the data 2, refused an answerable question 1
- v3: none

## Failures by brand

- fernwood-goods: v1: wrong_number 2, wrong_date 1, unsupported_number 1; v2: wrong_number 2, unsupported_number 2
- portfolio: v1: format_error 10
- saltmarsh-apparel: v1: wrong_number 1
- tidewater-swim: v2: false_abstention 1
