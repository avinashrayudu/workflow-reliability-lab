# mock run

**OFFLINE MOCK (oracle). Not model results: a perfect score shows every question is answerable through each variant's interface and the reference solutions agree with the truth file.**

Model: mock-oracle. Runs per question: 3. Token counts are estimates (about 4 characters per token); cost is priced as claude-sonnet-5-5 from config/models.yaml (mock output is shorter than a real model writes, so read cost as a floor).

| metric | v1 | v2 | v3 |
|---|---|---|---|
| accuracy (all runs) | 1.0 | 1.0 | 1.0 |
| questions right every run | 33 | 33 | 33 |
| consistency: all runs agree | 1.0 | 1.0 | 1.0 |
| consistency: modal share | 1.0 | 1.0 | 1.0 |
| median numeric error % | 0.0 | 0.0 | 0.0 |
| mean numeric error % | 0.0 | 0.0 | 0.0 |
| abstentions correct | 12/12 | 12/12 | 12/12 |
| false abstentions | 0 | 0 | 0 |
| brief fields correct | 24/24 | 24/24 | 24/24 |
| brief unsupported $ figures | 0 | 0 | 0 |
| validator revisions | 0 | 0 | 0 |
| validator forced abstentions | 0 | 0 | 0 |
| input tokens | 3816792 | 212250 | 691917 |
| output tokens | 4197 | 13887 | 11109 |
| cost USD | 7.6756 | 0.5634 | 1.4949 |
| cost per question USD | 0.07525 | 0.00552 | 0.01466 |
| mean turns | 1 | 2 | 3.24 |
| median latency s | 0.025 | 0.0 | 0.001 |

## Outcomes

- v1: correct 99
- v2: correct 99
- v3: correct 99

## Failures by brand

- none
