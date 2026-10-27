---
name: credit-line
description: Draw size to hold the buffer, interest on a draw, and paydown vs sweep.
---
# Credit line

- **Draw to hold the buffer:** `cash_path(...).draw_to_hold_buffer`. To start from a gap, use `credit_math(op="draw_for_gap", gap=...)`. Draws are multiples of $25,000.
- **Interest on a draw:** `credit_math(op="interest", amount=..., weeks=...)`. This is simple interest at the brand's APR.
- **Paydown vs sweep:** `credit_math(op="paydown_vs_sweep")`. It defaults to the whole drawn balance. Read `annual_benefit_of_paydown`.
