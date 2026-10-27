---
name: bills-and-discounts
description: AP bills, due weeks, largest bill in a week, early-pay discounts and their deadlines.
---
# Bills and discounts

1. **Find bills:**
   - `bills(brand_id, due_week_start=...)` for a week. `largest` is the biggest bill due that week.
   - `bills(brand_id, bill_id=...)` for one bill.
2. **Discount:** use `discount_amount`, which is amount x discount_pct, and `discount_deadline_week_start`.
3. **Cash totals:** for "total cash out in a week", use the cash-position or variance tools, not bills. Cash out also includes payroll, card autopay and taxes.
4. **Not connected:** if `bills` says `"missing_data": true`, AP is not connected for that brand. Abstain, and do not guess a due date.
