---
name: variance-drivers
description: Actual minus forecast for a cash line, for all cash, by SKU refunds or by ad platform.
---
# Variance and drivers

## Which tool
- **One cash line or all cash lines:** `variance(brand_id, line, from_week_start, to_week_start)`.
  - Use `line="all"` for total variance.
  - "Weeks 0 to 2" means 2026-10-26 to 2026-11-09.
  - One week means from = to = that week_start.
- **Which SKU drove refunds:** `driver_variance(kind="refunds_by_sku")`. Read `largest_overrun` and `largest_overrun_amount`, or `items` for a named SKU.
- **Ad overspend by platform:** `driver_variance(kind="ad_spend")`, then read the platform's `variance_actual_minus_forecast`.
- **A single actual amount** (not a variance), such as an Amazon settlement received: `week_lines(basis="actual")` and read `lines`.

## Signs
- **Cash lines:** negative variance means less cash than forecast.
- **Refunds and ad spend:** these are spend amounts, so a positive variance means more was refunded or spent.

## Missing data
If a result says `"missing_data": true`, abstain. That covers a missing week, or SKU refunds that are not connected.
