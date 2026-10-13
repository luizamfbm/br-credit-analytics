-- The maturity buckets must add up to the current portfolio,
-- and the overdue buckets must add up to the overdue portfolio.
select portfolio_row_key
from {{ ref('fct_credit_portfolio_monthly') }}
where abs(
        current_up_to_90d + current_91_to_360d + current_361_to_1080d
      + current_1081_to_1800d + current_1801_to_5400d + current_over_5400d
      - current_portfolio) > 0.01
   or abs(overdue_15_to_90d + overdue_over_90d - overdue_portfolio) > 0.01
