---
name: data-gaps
description: Decide whether a question can be answered at all. Use it whenever a brand might be missing data.
---
# Data gaps

Call `check_coverage(brand_id)`. A question cannot be answered when it needs any of these:
- a week marked "not received";
- a source marked "not connected";
- a NULL actual.

When that happens, return `{"answer": null, "abstain": true, ...}`.

Do not abstain just because a different source is missing. For example, Saltmarsh Apparel's forecast cash path exists even though its AP bills are not connected.
