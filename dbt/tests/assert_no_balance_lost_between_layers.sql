-- Completeness: for every month, the total outstanding balance in the fact table
-- must match the staging layer. Catches rows dropped by joins or incremental filters.
with stg as (
    select reference_date as month_date, sum(outstanding_portfolio) as total
    from {{ ref('stg_scr__credit_portfolio') }}
    group by 1
),

fct as (
    select month_date, sum(outstanding_portfolio) as total
    from {{ ref('fct_credit_portfolio_monthly') }}
    group by 1
)

select
    stg.month_date,
    stg.total as staging_total,
    fct.total as fact_total
from stg
left join fct on fct.month_date = stg.month_date
where fct.total is null or abs(stg.total - fct.total) > 1
