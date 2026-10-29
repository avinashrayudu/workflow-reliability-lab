# Changelog

Each release is a git tag. Version 1.0.0 is reserved for the first live run. Built by Avinash Rayudu.

## How commits are structured

From v0.2.0 on, every commit message starts with its type:

| Type | Used for |
|---|---|
| `feat:` | new behavior in the variants, agent loop, harness or scorer |
| `fix:` | a bug fix; the message names what was wrong |
| `results:` | output of a run, committed as it came out; nothing else in the commit. A live run is always its own `results:` commit. |
| `docs:` | README and docs only; no number changes without a matching `results:` commit |
| `chore:` | tooling, tags, housekeeping |

## v0.2.0 (2026-10-28): ready for the live run

- feat: live-run guards: a spend cap (`MAX_USD`, default $40), no overwrite of a live result, provenance (git
  commit and hashes of data, questions and answer key) in every summary.
- feat: `make live-check`, a preflight that prints READY or PENDING without any model call.
- results: mock and faulty runs regenerated with provenance; scores unchanged.
- docs: `docs/live_run.md`; the so-what at the top of the README; plain-language thresholds; where the project fits
  at Highbeam; finance concepts; how it was built.

## v0.1.0 (2026-10-27): harness-validated, not live

- `7b96be7` three variants, 33 graded questions plus the brief, harness, scorer and offline mock.
- `0d59fb5` docs: three-line summary, plain status, report link, draw cross-reference, why these numbers.
