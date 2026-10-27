---
name: cash-position
description: Closing cash, low points, gap to buffer and ending cash, on the week-0 forecast or the roll-forward.
---
# Cash position

Use this for questions about closing cash, the low point and its week, the gap to the buffer, or ending cash.

## Steps
1. Pick the basis.
   - "Week-0 forecast", or a plain forecast question: `basis=forecast`. The low point covers all 13 weeks.
   - "Roll-forward", "actual closing cash", or anything from today onward: `basis=rollforward`. The low point covers the week of 2026-11-16 onward.
2. Call `cash_path(brand_id, basis)`. Read these keys:
   - `low_point`, `low_point_week`, `gap_to_buffer`, `draw_to_hold_buffer`, `ending_cash`
   - `weeks[i].closing_cash`, which gives the actual closing cash at the end of a past week on the roll-forward basis.
3. If the result has `"missing_data": true`, abstain. Never fill a missing week with the forecast.

## Pitfalls
- `ad_spend_accrual` is not cash. The tool already leaves it out.
- The answer is the tool's number. Do not re-add the weeks by hand.
