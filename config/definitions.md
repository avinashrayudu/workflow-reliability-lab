# Definitions every variant receives

You answer questions about the weekly cash of 10 consumer products brands. Today is Monday, November 16, 2026.

## The data
- Actuals run through Sunday, November 15, 2026: weeks 0, 1 and 2.
- The forecast was made on October 26, 2026 (week 0) and covers 13 weeks, through the week of January 18, 2027.
- A week is identified by the date of its Monday (`week_start`, e.g. 2026-11-16) or by `week_index` (0 to 12).

## Cash conventions
- **Cash lines** are the rows of `weekly_cash` with `is_cash = 1`. Positive amounts are cash in; negative amounts are cash out.
- `ad_spend_accrual` has `is_cash = 0`. It is card spend that is not cash yet, and it never counts toward cash.
- **Closing cash** for a week = the brand's `opening_cash` + the sum of all cash lines from week 0 through that week.
- **Week-0 forecast** uses the `forecast` column for every week.
- **Roll-forward** uses `actual` for weeks 0 to 2 and `forecast` from the week of November 16 onward.
  - It needs actuals for all of weeks 0 to 2.
  - The **roll-forward low point** is the lowest closing cash from the week of November 16 onward.
- **Low point:** the lowest closing cash over the stated weeks. Its week is the `week_start` where it happens.
- **Gap to buffer** = `cash_buffer` minus the low point. It is zero if the low point is at or above the buffer.

## Variance, draws and bills
- **Variance** = actual minus forecast. Negative means less cash than forecast.
  - For `ad_spend` and `refunds_by_sku`, amounts are positive spend. Their variance (actual minus forecast) is positive when more was spent or refunded than planned.
- **Credit draw to hold the buffer** = the gap to buffer rounded up to the next multiple of $25,000.
- **Interest on a draw** = amount x `loc_apr` x weeks / 52 (simple interest).
- **Early-pay discount** on a bill = `amount` x `discount_pct`. The bill must be paid by `discount_deadline_week_start`.

## How to answer
- Money answers are dollars. Give them to the cent or the dollar, as a plain number with no $ sign or commas. Dates are YYYY-MM-DD. Brands are their `brand_id`.
- **Missing data:** if the data needed to answer is missing, you must abstain rather than estimate. Missing data means a NULL actual, a source marked "not connected" in `data_coverage`, or a week not received.

Finish with one JSON object on its own line, and nothing after it:

```
{"answer": <number | "text" | ["list", "of", "items"] | null>, "abstain": <true | false>, "reason": "<one sentence>"}
```
