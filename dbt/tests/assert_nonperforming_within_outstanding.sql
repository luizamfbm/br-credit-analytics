-- Nonperforming and problem assets are subsets of the outstanding portfolio.
select portfolio_row_key
from {{ ref('fct_credit_portfolio_monthly') }}
where nonperforming_portfolio > outstanding_portfolio + 0.01
   or nonperforming_portfolio < 0
   or outstanding_portfolio < 0
