---
name: portfolio
description: Questions across all 10 brands.
---
# Portfolio

- **Which brands sit below their buffer:** `portfolio(metric="low_point_vs_buffer")`. Read:
  - `count_below_buffer`
  - `lowest_ratio_brand`
  - each brand's `ratio`
- **Which brands have no amounts on a line:** `portfolio(metric="brands_without_line", line=...)`. Read `brands`.

Answer with `brand_id` values.
