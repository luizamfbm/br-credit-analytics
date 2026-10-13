-- Outstanding portfolio must equal current + overdue on every row (tolerance: 1 cent).
-- Returns the rows that break the rule; the test passes when it returns nothing.
select
    portfolio_row_key,
    outstanding_portfolio,
    current_portfolio,
    overdue_portfolio
from {{ ref('fct_credit_portfolio_monthly') }}
where abs(outstanding_portfolio - (current_portfolio + overdue_portfolio)) > 0.01
