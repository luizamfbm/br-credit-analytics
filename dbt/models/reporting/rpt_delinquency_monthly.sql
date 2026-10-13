{#
  Dashboard-ready table (Tableau / Power BI / Looker Studio).
  Grain: month x state x customer type x product group.
  The rate is computed from summed balances, never by averaging rates.
#}
select
    m.month_date,
    m.year,
    m.month,
    s.state_code,
    s.state_name,
    s.region,
    c.customer_type,
    p.product_group,
    sum(f.outstanding_portfolio)                                  as outstanding_portfolio,
    sum(f.overdue_over_90d)                                       as overdue_over_90d,
    sum(f.nonperforming_portfolio)                                as nonperforming_portfolio,
    sum(f.number_of_operations)                                   as disclosed_operations,
    sum(case when f.is_operations_undisclosed then 1 else 0 end)  as rows_with_undisclosed_operations,
    sum(f.nonperforming_portfolio) / nullif(sum(f.outstanding_portfolio), 0) as nonperforming_rate
from {{ ref('fct_credit_portfolio_monthly') }} f
join {{ ref('dim_month') }}            m on m.month_key = f.month_key
join {{ ref('dim_state') }}            s on s.state_key = f.state_key
join {{ ref('dim_customer_profile') }} c on c.customer_profile_key = f.customer_profile_key
join {{ ref('dim_product') }}          p on p.product_key = f.product_key
group by 1, 2, 3, 4, 5, 6, 7, 8
